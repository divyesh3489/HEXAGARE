"""Reports + exports API (Phase 14) -- RBAC, endpoint shapes, export flow."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.reports.models import ReportExport
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class ReportsApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        cls.warehouse = Location.objects.get(code="warehouse")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            purchase_price=Decimal("400.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def complete_offline_sale(self):
        unit = create_unit(
            variant=self.variant,
            location=self.warehouse,
            status=SerializedUnit.Status.AVAILABLE,
            purchase_cost=Decimal("300.00"),
        )
        sale = Sale.objects.create(sales_channel=self.offline)
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )
        return sale, unit


class RbacTests(ReportsApiTestBase):
    def test_cashier_cannot_view_reports(self):
        res = self.client_for(self.cashier).get(
            "/api/v1/reports/sales/?date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 403)

    def test_cashier_cannot_create_export(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/reports/exports/",
            {
                "report_type": "FINANCIAL",
                "export_format": "CSV",
                "filters": {"date_from": "2026-01-01", "date_to": "2026-01-31"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_manager_can_view_reports(self):
        res = self.client_for(self.manager).get(
            "/api/v1/reports/sales/?date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 200)


class SalesReportEndpointTests(ReportsApiTestBase):
    def test_requires_date_range(self):
        res = self.client_for(self.manager).get("/api/v1/reports/sales/")
        self.assertEqual(res.status_code, 400)

    def test_rejects_unknown_channel(self):
        res = self.client_for(self.manager).get(
            "/api/v1/reports/sales/?date_from=2026-01-01&date_to=2026-01-31&channel=FLIPKART"
        )
        self.assertEqual(res.status_code, 400)

    def test_grouped_rows(self):
        self.complete_offline_sale()
        res = self.client_for(self.manager).get(
            "/api/v1/reports/sales/"
            "?date_from=2026-01-01&date_to=2026-12-31&group_by=variant"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["summary"]["orders"], 1)
        self.assertEqual(len(res.data["rows"]), 1)
        self.assertEqual(res.data["rows"][0]["name"], "HEX-MP-A-001")


class InventoryReportEndpointTests(ReportsApiTestBase):
    def test_current_stock(self):
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        res = self.client_for(self.manager).get("/api/v1/reports/inventory/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["summary"]["by_status"]["AVAILABLE"], 1)

    def test_movement_view_requires_date_range(self):
        res = self.client_for(self.manager).get("/api/v1/reports/inventory/?view=movement")
        self.assertEqual(res.status_code, 400)


class SerialNumberHistoryEndpointTests(ReportsApiTestBase):
    def test_requires_serial_number(self):
        res = self.client_for(self.manager).get("/api/v1/reports/serial-number-history/")
        self.assertEqual(res.status_code, 400)

    def test_returns_the_lifecycle(self):
        _sale, unit = self.complete_offline_sale()
        res = self.client_for(self.manager).get(
            f"/api/v1/reports/serial-number-history/?serial_number={unit.serial_number}"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["summary"]["serial_number"], unit.serial_number)

    def test_unknown_serial_number_is_a_400(self):
        res = self.client_for(self.manager).get(
            "/api/v1/reports/serial-number-history/?serial_number=DOES-NOT-EXIST"
        )
        self.assertEqual(res.status_code, 400)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ExportFlowTests(ReportsApiTestBase):
    def test_create_export_runs_synchronously_and_downloads(self):
        self.complete_offline_sale()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.manager).post(
                "/api/v1/reports/exports/",
                {
                    "report_type": "SALES",
                    "export_format": "CSV",
                    "filters": {
                        "date_from": "2026-01-01",
                        "date_to": "2026-12-31",
                        "group_by": "variant",
                    },
                },
                format="json",
            )
        self.assertEqual(res.status_code, 201, res.data)
        export_id = res.data["id"]

        # The render runs on commit -- the create response itself is still
        # PENDING; check the row again once the callback (above) has run.
        detail = self.client_for(self.manager).get(f"/api/v1/reports/exports/{export_id}/")
        self.assertEqual(detail.data["status"], ReportExport.Status.READY)
        self.assertIsNotNone(detail.data["download_url"])

        download = self.client_for(self.manager).get(
            f"/api/v1/reports/exports/{export_id}/download/"
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"HEX-MP-A-001", download.content)

    def test_excel_export(self):
        self.complete_offline_sale()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.manager).post(
                "/api/v1/reports/exports/",
                {
                    "report_type": "FINANCIAL",
                    "export_format": "XLSX",
                    "filters": {"date_from": "2026-01-01", "date_to": "2026-12-31"},
                },
                format="json",
            )
        self.assertEqual(res.status_code, 201, res.data)
        detail = self.client_for(self.manager).get(f"/api/v1/reports/exports/{res.data['id']}/")
        self.assertEqual(detail.data["status"], ReportExport.Status.READY)

    def test_invalid_filters_fail_before_creating_the_export(self):
        res = self.client_for(self.manager).post(
            "/api/v1/reports/exports/",
            {"report_type": "SALES", "export_format": "CSV", "filters": {}},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ReportExport.objects.count(), 0)

    def test_list_exports(self):
        ReportExport.objects.create(
            report_type=ReportExport.ReportType.FINANCIAL,
            export_format=ReportExport.ExportFormat.CSV,
            filters={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        )
        res = self.client_for(self.manager).get("/api/v1/reports/exports/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["meta"]["count"], 1)
