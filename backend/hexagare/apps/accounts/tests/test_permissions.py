from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.accounts.permissions import HasOperationalPermission, require
from apps.accounts.rbac import ensure_role_groups

User = get_user_model()


class _PosView(APIView):
    permission_classes = [require("pos")]

    def get(self, request):
        return Response({"ok": True})


class _NeedsBothView(APIView):
    permission_classes = [require("inventory.view", "stock_adjustments")]

    def get(self, request):
        return Response({"ok": True})


class _SubclassView(APIView):
    class _Perm(HasOperationalPermission):
        required_permissions = ("barcode.scan",)

    permission_classes = [_Perm]

    def get(self, request):
        return Response({"ok": True})


class HasOperationalPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.factory = APIRequestFactory()
        cls.nobody = User.objects.create_user("nobody@hexagare.test", "pw-Testing-123")
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse.groups.add(Group.objects.get(name="Warehouse"))
        cls.superuser = User.objects.create_superuser("root@hexagare.test", "pw-Testing-123")

    def _get(self, view, user=None):
        request = self.factory.get("/x/")
        if user is not None:
            force_authenticate(request, user=user)
        return view(request)

    def test_anonymous_gets_401(self):
        self.assertEqual(self._get(_PosView.as_view()).status_code, 401)

    def test_authenticated_without_permission_gets_403(self):
        self.assertEqual(self._get(_PosView.as_view(), self.nobody).status_code, 403)

    def test_role_holding_permission_passes(self):
        self.assertEqual(self._get(_PosView.as_view(), self.cashier).status_code, 200)

    def test_superuser_always_passes(self):
        self.assertEqual(self._get(_PosView.as_view(), self.superuser).status_code, 200)

    def test_all_of_multiple_permissions_required(self):
        # Cashier has neither inventory.view nor stock_adjustments.
        self.assertEqual(self._get(_NeedsBothView.as_view(), self.cashier).status_code, 403)
        # Warehouse has both.
        self.assertEqual(self._get(_NeedsBothView.as_view(), self.warehouse).status_code, 200)

    def test_subclass_form(self):
        self.assertEqual(self._get(_SubclassView.as_view(), self.nobody).status_code, 403)
        self.assertEqual(self._get(_SubclassView.as_view(), self.cashier).status_code, 200)
