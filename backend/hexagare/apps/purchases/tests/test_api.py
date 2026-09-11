"""Purchases API (Phase 12) -- create/line-lock/place/cancel, receive-stock
atomicity + cost-basis + status transitions, payments, RBAC."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import OperationalPermission
from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.purchases.models import PurchaseOrder
from apps.suppliers.models import Supplier

User = get_user_model()


class PurchasesApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))
        cls.warehouse_user = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        # Every seed role holding purchases.manage (Admin/Manager) also holds
        # purchases_receiving -- grant purchases.manage alone to exercise the
        # split between "can create/edit orders" and "can receive stock".
        cls.order_manager_only = User.objects.create_user(
            "order-manager@hexagare.test", "pw-Testing-123"
        )
        content_type = ContentType.objects.get_for_model(OperationalPermission)
        cls.order_manager_only.user_permissions.add(
            Permission.objects.get(content_type=content_type, codename="purchases.view"),
            Permission.objects.get(content_type=content_type, codename="purchases.manage"),
        )

        cls.warehouse = Location.objects.get(code="warehouse")
        cls.supplier = Supplier.objects.create(name="Acme Supplies")
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

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def create_order(self, user=None, quantity=10, unit_price="100.00"):
        user = user or self.manager
        res = self.client_for(user).post(
            "/api/v1/purchases/orders/",
            {
                "supplier": self.supplier.id,
                "reference": "PO-1",
                "lines": [
                    {
                        "variant": self.variant.id,
                        "quantity_ordered": quantity,
                        "unit_price": unit_price,
                        "tax_rate": "18.00",
                    }
                ],
            },
            format="json",
        )
        return res


class RbacTests(PurchasesApiTestBase):
    def test_warehouse_can_view_but_not_create(self):
        res = self.client_for(self.warehouse_user).get("/api/v1/purchases/orders/")
        self.assertEqual(res.status_code, 200)
        res = self.create_order(user=self.warehouse_user)
        self.assertEqual(res.status_code, 403)

    def test_cashier_has_no_purchases_access(self):
        res = self.client_for(self.cashier).get("/api/v1/purchases/orders/")
        self.assertEqual(res.status_code, 403)

    def test_receive_requires_purchases_receiving(self):
        res = self.create_order()
        order_id = res.data["id"]
        line_id = res.data["lines"][0]["id"]
        self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        res = self.client_for(self.order_manager_only).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 1, "location": self.warehouse.id}]},
            format="json",
        )
        # purchases.manage alone doesn't cover receiving stock.
        self.assertEqual(res.status_code, 403)


class CreateAndLineLockTests(PurchasesApiTestBase):
    def test_create_with_nested_lines_computes_totals(self):
        res = self.create_order(quantity=10, unit_price="100.00")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], PurchaseOrder.Status.DRAFT)
        # 10 * 100 = 1000 gross, tax-inclusive convention backs out GST from it.
        self.assertEqual(res.data["grand_total"], "1000.00")
        line = res.data["lines"][0]
        self.assertEqual(line["quantity_pending"], 10)

    def test_lines_editable_while_draft(self):
        order_id = self.create_order().data["id"]
        order = self.client_for(self.manager).get(f"/api/v1/purchases/orders/{order_id}/").data
        line_id = order["lines"][0]["id"]
        res = self.client_for(self.manager).patch(
            f"/api/v1/purchases/orders/{order_id}/lines/{line_id}/",
            {"quantity_ordered": 20},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["lines"][0]["quantity_ordered"], 20)

    def test_lines_locked_once_placed(self):
        order_id = self.create_order().data["id"]
        self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        order = self.client_for(self.manager).get(f"/api/v1/purchases/orders/{order_id}/").data
        line_id = order["lines"][0]["id"]
        res = self.client_for(self.manager).patch(
            f"/api/v1/purchases/orders/{order_id}/lines/{line_id}/",
            {"quantity_ordered": 20},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_place_requires_at_least_one_line(self):
        res = self.client_for(self.manager).post(
            "/api/v1/purchases/orders/", {"supplier": self.supplier.id}, format="json"
        )
        order_id = res.data["id"]
        res = self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        self.assertEqual(res.status_code, 400)


class ReceiveStockTests(PurchasesApiTestBase):
    def _placed_order(self, quantity=10, unit_price="100.00"):
        res = self.create_order(quantity=quantity, unit_price=unit_price)
        order_id = res.data["id"]
        line_id = res.data["lines"][0]["id"]
        self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        return order_id, line_id

    def test_partial_then_full_receive_updates_status_and_cost_basis(self):
        order_id, line_id = self._placed_order(quantity=5, unit_price="250.00")

        res = self.client_for(self.warehouse_user).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 3, "location": self.warehouse.id}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.assertEqual(res.data["lines"][0]["quantity_received"], 3)
        self.assertEqual(len(res.data["lines"][0]["units"]), 3)

        units = SerializedUnit.objects.filter(variant=self.variant)
        self.assertEqual(units.count(), 3)
        for unit in units:
            self.assertEqual(unit.purchase_cost, Decimal("250.00"))
            self.assertEqual(unit.status, SerializedUnit.Status.AVAILABLE)
            self.assertEqual(unit.location_id, self.warehouse.id)

        res = self.client_for(self.warehouse_user).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 2, "location": self.warehouse.id}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], PurchaseOrder.Status.RECEIVED)
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 5)

    def test_receive_more_than_pending_is_rejected(self):
        order_id, line_id = self._placed_order(quantity=2)
        res = self.client_for(self.warehouse_user).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 3, "location": self.warehouse.id}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 0)

    def test_cannot_receive_against_draft_order(self):
        res = self.create_order(quantity=2)
        order_id = res.data["id"]
        line_id = res.data["lines"][0]["id"]
        res = self.client_for(self.warehouse_user).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 1, "location": self.warehouse.id}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class PaymentAndCancelTests(PurchasesApiTestBase):
    def test_record_payment_updates_balance_due(self):
        order_id = self.create_order(quantity=10, unit_price="100.00").data["id"]
        res = self.client_for(self.manager).post(
            f"/api/v1/purchases/orders/{order_id}/payments/",
            {"method": "BANK_TRANSFER", "amount": "400.00"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["amount_paid"], "400.00")
        self.assertEqual(res.data["balance_due"], "600.00")

    def test_cancel_from_ordered(self):
        order_id = self.create_order().data["id"]
        self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        res = self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/cancel/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], PurchaseOrder.Status.CANCELLED)

    def test_cancel_from_received_is_rejected(self):
        res = self.create_order(quantity=1)
        order_id = res.data["id"]
        line_id = res.data["lines"][0]["id"]
        self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/place/")
        self.client_for(self.warehouse_user).post(
            f"/api/v1/purchases/orders/{order_id}/receive/",
            {"receipts": [{"line": line_id, "quantity": 1, "location": self.warehouse.id}]},
            format="json",
        )
        res = self.client_for(self.manager).post(f"/api/v1/purchases/orders/{order_id}/cancel/")
        self.assertEqual(res.status_code, 400)
