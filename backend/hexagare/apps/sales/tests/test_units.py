"""SaleLineUnit binding -- scan/search add, remove, race safety, cancel-release
(Phase 8, ADR-013)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.products.services.serialized_inventory import SerializedInventoryService
from apps.sales.models import Sale, SaleLineUnit, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class SaleUnitServiceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
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

    def make_unit(self, status=SerializedUnit.Status.AVAILABLE):
        return create_unit(variant=self.variant, location=self.warehouse, status=status)

    def make_sale(self):
        return Sale.objects.create(sales_channel=self.offline)


class ServiceLevelTests(SaleUnitServiceTestBase):
    def test_add_by_code_reserves_and_creates_line(self):
        sale = self.make_sale()
        unit = self.make_unit()

        line = SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.RESERVED)
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.variant_id, self.variant.pk)
        self.assertTrue(SaleLineUnit.objects.filter(sale_line=line, serialized_unit=unit).exists())

        sale.refresh_from_db()
        self.assertEqual(sale.grand_total, Decimal("1180.00"))

    def test_second_scan_of_same_variant_reuses_line(self):
        sale = self.make_sale()
        u1, u2 = self.make_unit(), self.make_unit()

        line1 = SaleUnitService.add(sale, code=u1.serial_number, actor=self.cashier)
        line2 = SaleUnitService.add(sale, code=u2.serial_number, actor=self.cashier)

        self.assertEqual(line1.pk, line2.pk)
        line1.refresh_from_db()
        self.assertEqual(line1.quantity, 2)

    def test_add_by_variant_picks_oldest_available(self):
        sale = self.make_sale()
        first = self.make_unit()
        self.make_unit()  # a second AVAILABLE unit, should not be picked

        line = SaleUnitService.add(sale, variant=self.variant, actor=self.cashier)
        bound = line.units.get().serialized_unit
        self.assertEqual(bound.pk, first.pk)

    def test_cannot_add_non_available_unit_by_code(self):
        sale = self.make_sale()
        unit = self.make_unit()
        SerializedInventoryService.reserve(unit, actor=self.cashier)
        SerializedInventoryService.sell(unit, actor=self.cashier)
        with self.assertRaises(ValidationError):
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

    def test_double_scan_of_same_unit_is_rejected(self):
        sale = self.make_sale()
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.assertRaises(ValidationError):
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

    def test_remove_releases_unit_and_deletes_empty_line(self):
        sale = self.make_sale()
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        SaleUnitService.remove(sale, unit.pk, actor=self.cashier)

        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.AVAILABLE)
        self.assertFalse(sale.lines.exists())
        self.assertFalse(SaleLineUnit.objects.filter(serialized_unit=unit).exists())

    def test_release_all_frees_every_bound_unit(self):
        sale = self.make_sale()
        u1, u2 = self.make_unit(), self.make_unit()
        SaleUnitService.add(sale, code=u1.serial_number, actor=self.cashier)
        SaleUnitService.add(sale, code=u2.serial_number, actor=self.cashier)

        SaleUnitService.release_all(sale, actor=self.cashier)

        u1.refresh_from_db()
        u2.refresh_from_db()
        self.assertEqual(u1.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(u2.status, SerializedUnit.Status.AVAILABLE)
        self.assertFalse(SaleLineUnit.objects.filter(sale_line__sale=sale).exists())

    def test_cannot_add_to_non_draft_sale(self):
        sale = self.make_sale()
        sale.status = Sale.Status.COMPLETED
        sale.save(update_fields=["status"])
        unit = self.make_unit()
        with self.assertRaises(ValidationError):
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)


class UnitApiTests(SaleUnitServiceTestBase):
    def test_scan_add_and_remove_via_api(self):
        client = self.client_for(self.cashier)
        sale = self.make_sale()
        unit = self.make_unit()

        res = client.post(
            f"/api/v1/sales/{sale.pk}/units/", {"code": unit.serial_number}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["grand_total"], "1180.00")

        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.RESERVED)

        res = client.delete(f"/api/v1/sales/{sale.pk}/units/{unit.pk}/")
        self.assertEqual(res.status_code, 200, res.data)
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.AVAILABLE)

    def test_line_delete_releases_bound_units(self):
        client = self.client_for(self.cashier)
        sale = self.make_sale()
        unit = self.make_unit()
        line = SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        res = client.delete(f"/api/v1/sales/{sale.pk}/lines/{line.pk}/")
        self.assertEqual(res.status_code, 200, res.data)
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.AVAILABLE)

    def test_manual_quantity_edit_rejected_once_unit_backed(self):
        client = self.client_for(self.cashier)
        sale = self.make_sale()
        unit = self.make_unit()
        line = SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        res = client.patch(
            f"/api/v1/sales/{sale.pk}/lines/{line.pk}/", {"quantity": 5}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_cancel_releases_bound_units(self):
        client = self.client_for(self.cashier)
        sale = self.make_sale()
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        res = client.post(f"/api/v1/sales/{sale.pk}/cancel/")
        self.assertEqual(res.status_code, 200, res.data)
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.AVAILABLE)
