"""Phase 17 -- Administration: business settings, user management, roles,
the activity/audit log, and manual DB backups."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import AuditLogEntry, BackupJob, BusinessSettings
from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.billing.services.returns import ReturnService
from apps.expenses.models import Expense
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService
from apps.suppliers.models import Supplier

User = get_user_model()

SETTINGS_URL = "/api/v1/auth/settings/"
USERS_URL = "/api/v1/auth/users/"
ROLES_URL = "/api/v1/auth/roles/"
AUDIT_URL = "/api/v1/auth/audit-log/"
BACKUPS_URL = "/api/v1/auth/backups/"


class AdministrationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.admin = User.objects.create_user("admin@hexagare.test", "pw-Testing-123")
        cls.admin.groups.add(Group.objects.get(name="Admin"))
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class BusinessSettingsTests(AdministrationTestBase):
    def test_get_is_open_to_any_authenticated_user(self):
        res = self.client_for(self.cashier).get(SETTINGS_URL)
        self.assertEqual(res.status_code, 200)
        self.assertIn("currency", res.data)

    def test_cashier_cannot_update_settings(self):
        res = self.client_for(self.cashier).patch(
            SETTINGS_URL, {"business_name": "Nope"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_admin_can_update_settings_and_it_is_a_singleton(self):
        res = self.client_for(self.admin).patch(
            SETTINGS_URL,
            {"business_name": "Hexagare Pads", "serial_prefix": "ACME", "serial_padding": 4},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["business_name"], "Hexagare Pads")
        self.assertEqual(BusinessSettings.objects.count(), 1)
        settings_row = BusinessSettings.objects.get(pk=1)
        self.assertEqual(settings_row.updated_by, self.admin)

    def test_updating_settings_writes_an_audit_log_entry(self):
        self.client_for(self.admin).patch(
            SETTINGS_URL, {"business_name": "Hexagare Pads"}, format="json"
        )
        entry = AuditLogEntry.objects.filter(
            action=AuditLogEntry.Action.SETTINGS_UPDATED
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertIn("business_name", entry.changes)

    def test_serial_prefix_override_is_read_by_serial_allocation(self):
        self.client_for(self.admin).patch(
            SETTINGS_URL, {"serial_prefix": "ZZZ"}, format="json"
        )
        location = Location.objects.filter(kind=Location.Kind.WAREHOUSE).first()
        category = Category.objects.create(name="Mouse Pads", code="MP")
        product = Product.objects.create(name="Widget", category=category)
        variant = ProductVariant.objects.create(product=product, code="W1", sku="HEX-W1-001")
        from apps.products.services.serial_numbers import create_unit

        unit = create_unit(variant=variant, location=location, actor=self.admin)
        self.assertTrue(unit.serial_number.startswith("ZZZ"))


class UserAdminTests(AdministrationTestBase):
    def test_manager_cannot_manage_users(self):
        res = self.client_for(self.manager).get(USERS_URL)
        self.assertEqual(res.status_code, 403)

    def test_admin_can_create_a_user_with_a_role(self):
        res = self.client_for(self.admin).post(
            USERS_URL,
            {
                "email": "newhire@hexagare.test",
                "password": "correct-horse-9-battery",
                "first_name": "New",
                "role": "Cashier",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        user = User.objects.get(email="newhire@hexagare.test")
        self.assertTrue(user.groups.filter(name="Cashier").exists())
        self.assertTrue(user.check_password("correct-horse-9-battery"))
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.USER_CREATED, object_id=str(user.pk)
            ).exists()
        )

    def test_duplicate_email_is_rejected(self):
        res = self.client_for(self.admin).post(
            USERS_URL,
            {
                "email": self.manager.email,
                "password": "correct-horse-9-battery",
                "role": "Cashier",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_admin_can_update_role_and_it_is_audited(self):
        res = self.client_for(self.admin).patch(
            f"{USERS_URL}{self.cashier.pk}/",
            {"role": "Warehouse", "first_name": "Renamed"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.groups.filter(name="Warehouse").exists())
        entry = AuditLogEntry.objects.filter(
            action=AuditLogEntry.Action.USER_UPDATED, object_id=str(self.cashier.pk)
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes["role"]["new"], "Warehouse")

    def test_deactivate_then_reactivate(self):
        client = self.client_for(self.admin)
        res = client.post(f"{USERS_URL}{self.cashier.pk}/deactivate/")
        self.assertEqual(res.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertFalse(self.cashier.is_active)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.USER_DEACTIVATED).exists()
        )

        res = client.post(f"{USERS_URL}{self.cashier.pk}/deactivate/")
        self.assertEqual(res.status_code, 400)

        res = client.post(f"{USERS_URL}{self.cashier.pk}/reactivate/")
        self.assertEqual(res.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.is_active)

    def test_filter_by_role_and_is_active(self):
        client = self.client_for(self.admin)
        res = client.get(f"{USERS_URL}?role=Cashier")
        emails = {row["email"] for row in res.data["data"]}
        self.assertIn(self.cashier.email, emails)
        self.assertNotIn(self.manager.email, emails)


class RolesViewTests(AdministrationTestBase):
    def test_manager_cannot_view_roles_matrix(self):
        res = self.client_for(self.manager).get(ROLES_URL)
        self.assertEqual(res.status_code, 403)

    def test_admin_sees_role_permission_matrix(self):
        res = self.client_for(self.admin).get(ROLES_URL)
        self.assertEqual(res.status_code, 200)
        roles = {row["role"] for row in res.data["roles"]}
        self.assertEqual(roles, {"Admin", "Manager", "Cashier", "Warehouse"})
        codenames = {row["codename"] for row in res.data["permissions"]}
        self.assertIn("settings.manage", codenames)


class AuditLogViewSetTests(AdministrationTestBase):
    def test_cashier_cannot_view_audit_log(self):
        res = self.client_for(self.cashier).get(AUDIT_URL)
        self.assertEqual(res.status_code, 403)

    def test_admin_can_list_and_filter_audit_log(self):
        self.client_for(self.admin).patch(
            SETTINGS_URL, {"business_name": "Hexagare Pads"}, format="json"
        )
        client = self.client_for(self.admin)
        res = client.get(AUDIT_URL)
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["meta"]["count"], 1)

        res = client.get(f"{AUDIT_URL}?action={AuditLogEntry.Action.SETTINGS_UPDATED}")
        self.assertEqual(len(res.data["data"]), 1)

        res = client.get(f"{AUDIT_URL}?action=user.created")
        self.assertEqual(len(res.data["data"]), 0)

    def test_audit_log_is_read_only(self):
        res = self.client_for(self.admin).post(
            AUDIT_URL, {"action": "user.created"}, format="json"
        )
        self.assertEqual(res.status_code, 405)


class DomainActivityIsLoggedTests(AdministrationTestBase):
    """Spot-checks that the service-layer hooks (not just the accounts app's
    own views) actually write an AuditLogEntry -- one per audited action
    family, not exhaustive per HEXAGARE_FEATURES.md section 53's full list."""

    def test_location_create_update_delete_are_logged(self):
        client = self.client_for(self.admin)
        res = client.post(
            "/api/v1/inventory/locations/",
            {"name": "Overflow Shelf", "code": "overflow-shelf", "kind": Location.Kind.WAREHOUSE},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        location_id = res.data["id"]
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.LOCATION_CREATED).exists()
        )

        client.patch(
            f"/api/v1/inventory/locations/{location_id}/", {"name": "Renamed"}, format="json"
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.LOCATION_UPDATED).exists()
        )

        client.delete(f"/api/v1/inventory/locations/{location_id}/")
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.LOCATION_DELETED).exists()
        )

    def test_manual_stock_adjustment_is_logged(self):
        location = Location.objects.filter(kind=Location.Kind.WAREHOUSE).first()
        category = Category.objects.create(name="Mouse Pads", code="MP")
        product = Product.objects.create(name="Widget", category=category)
        variant = ProductVariant.objects.create(product=product, code="W2", sku="HEX-W2-001")
        client = self.client_for(self.admin)
        res = client.post(
            "/api/v1/inventory/adjustments/",
            {
                "variant": variant.pk,
                "location": location.pk,
                "status": SerializedUnit.Status.AVAILABLE,
                "quantity": 5,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.STOCK_CHANGED).exists()
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class BackupTests(AdministrationTestBase):
    def test_cashier_cannot_trigger_a_backup(self):
        res = self.client_for(self.cashier).post(BACKUPS_URL)
        self.assertEqual(res.status_code, 403)

    def test_admin_triggers_a_backup_and_it_is_audited(self):
        # `patch` must be the OUTER context manager -- `with A, B:` exits B
        # (captureOnCommitCallbacks, which runs the captured on_commit
        # callback on __exit__) before A, so the mock has to still be
        # active at that point or the on_commit callback runs a real pg_dump.
        with patch("apps.accounts.tasks.subprocess.run") as mock_run, \
                self.captureOnCommitCallbacks(execute=True):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = b""
            res = self.client_for(self.admin).post(BACKUPS_URL)
        self.assertEqual(res.status_code, 201)
        job = BackupJob.objects.get(pk=res.data["id"])
        self.assertEqual(job.status, BackupJob.Status.SUCCESS)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.BACKUP_TRIGGERED).exists()
        )

    def test_a_failed_pg_dump_records_the_error(self):
        with patch("apps.accounts.tasks.subprocess.run") as mock_run, \
                self.captureOnCommitCallbacks(execute=True):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = b"pg_dump: connection failed"
            res = self.client_for(self.admin).post(BACKUPS_URL)
        job = BackupJob.objects.get(pk=res.data["id"])
        self.assertEqual(job.status, BackupJob.Status.FAILED)
        self.assertIn("connection failed", job.error_message)

    def test_download_is_rejected_until_the_backup_succeeds(self):
        job = BackupJob.objects.create(triggered_by=self.admin)
        res = self.client_for(self.admin).get(f"{BACKUPS_URL}{job.pk}/download/")
        self.assertEqual(res.status_code, 400)

    def test_history_lists_backups_newest_first(self):
        older = BackupJob.objects.create(triggered_by=self.admin, status=BackupJob.Status.SUCCESS)
        newer = BackupJob.objects.create(triggered_by=self.admin, status=BackupJob.Status.SUCCESS)
        res = self.client_for(self.admin).get(BACKUPS_URL)
        ids = [row["id"] for row in res.data["data"]]
        self.assertEqual(ids[:2], [newer.pk, older.pk])


class CrossAppActivityIsLoggedTests(AdministrationTestBase):
    """Further spot-checks (see also ``DomainActivityIsLoggedTests`` above)
    that the log_activity hooks added to apps.sales/billing/purchases/
    expenses actually fire -- one per action family, not exhaustive."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = SalesChannel.objects.get(code="OFFLINE")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )

    def make_unit(self):
        return create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )

    def make_sold_unit(self):
        """A unit sold through the real checkout flow -- for the returns test."""
        sale = Sale.objects.create(sales_channel=self.offline)
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.manager)
        with self.captureOnCommitCallbacks(execute=True):
            sale, invoice = CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.manager,
            )
        unit.refresh_from_db()
        return sale, unit

    def test_order_created_and_cancelled_are_logged(self):
        client = self.client_for(self.manager)
        res = client.post(
            "/api/v1/sales/", {"sales_channel": self.offline.pk}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        sale_id = res.data["id"]
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.ORDER_CREATED, object_id=str(sale_id)
            ).exists()
        )

        res = client.post(f"/api/v1/sales/{sale_id}/cancel/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.ORDER_CANCELLED, object_id=str(sale_id)
            ).exists()
        )

    def test_checkout_completion_logs_payment_and_invoice(self):
        sale, unit = self.make_sold_unit()
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.PAYMENT_RECORDED).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.INVOICE_CREATED).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.STATUS_CHANGED,
                content_type__model="serializedunit",
                object_id=str(unit.pk),
            ).exists()
        )

    def test_return_creation_is_logged(self):
        sale, unit = self.make_sold_unit()
        ReturnService.create(
            entries=[{"code": unit.serial_number}],
            reason="Customer changed their mind",
            refund_method=Payment.Method.CASH,
            actor=self.manager,
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.RETURN_CREATED).exists()
        )

    def test_purchase_order_lifecycle_is_logged(self):
        supplier = Supplier.objects.create(name="Acme Supplies")
        client = self.client_for(self.manager)
        res = client.post(
            "/api/v1/purchases/orders/",
            {
                "supplier": supplier.id,
                "lines": [
                    {
                        "variant": self.variant.id,
                        "quantity_ordered": 5,
                        "unit_price": "100.00",
                        "tax_rate": "18.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        order_id = res.data["id"]
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.PURCHASE_CREATED, object_id=str(order_id)
            ).exists()
        )

        res = client.post(
            f"/api/v1/purchases/orders/{order_id}/payments/",
            {"method": "CASH", "type": "PAYMENT", "amount": "100.00"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.PAYMENT_RECORDED).exists()
        )

        res = client.post(f"/api/v1/purchases/orders/{order_id}/cancel/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.PURCHASE_CANCELLED, object_id=str(order_id)
            ).exists()
        )

    def test_expense_create_update_delete_are_logged(self):
        client = self.client_for(self.manager)
        res = client.post(
            "/api/v1/expenses/",
            {
                "category": Expense.Category.OTHER,
                "amount": "50.00",
                "expense_date": "2026-01-15",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        expense_id = res.data["id"]
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.EXPENSE_CREATED, object_id=str(expense_id)
            ).exists()
        )

        res = client.patch(
            f"/api/v1/expenses/{expense_id}/", {"amount": "75.00"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.EXPENSE_UPDATED).exists()
        )

        res = client.delete(f"/api/v1/expenses/{expense_id}/")
        self.assertEqual(res.status_code, 204)
        self.assertTrue(
            AuditLogEntry.objects.filter(action=AuditLogEntry.Action.EXPENSE_DELETED).exists()
        )
