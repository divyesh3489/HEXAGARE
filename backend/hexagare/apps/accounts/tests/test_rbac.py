from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import OperationalPermission
from apps.accounts.rbac import (
    OPERATIONAL_PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLES,
    ensure_role_groups,
)


class EnsureRoleGroupsTests(TestCase):
    def _codenames(self, role: str) -> set[str]:
        return set(Group.objects.get(name=role).permissions.values_list("codename", flat=True))

    def test_creates_one_group_per_role(self):
        ensure_role_groups()
        for role in ROLES:
            self.assertTrue(Group.objects.filter(name=role).exists(), role)

    def test_admin_holds_every_operational_permission(self):
        ensure_role_groups()
        self.assertEqual(self._codenames("Admin"), set(OPERATIONAL_PERMISSIONS))

    def test_manager_excludes_user_and_settings_admin(self):
        ensure_role_groups()
        codenames = self._codenames("Manager")
        self.assertNotIn("users.manage", codenames)
        self.assertNotIn("settings.manage", codenames)
        self.assertIn("reports.export", codenames)

    def test_cashier_scope(self):
        ensure_role_groups()
        codenames = self._codenames("Cashier")
        self.assertIn("pos", codenames)
        self.assertIn("returns", codenames)
        self.assertNotIn("settings.manage", codenames)
        self.assertNotIn("stock_adjustments", codenames)

    def test_warehouse_scope(self):
        ensure_role_groups()
        codenames = self._codenames("Warehouse")
        self.assertIn("stock_adjustments", codenames)
        self.assertIn("purchases_receiving", codenames)
        self.assertNotIn("pos", codenames)

    def test_permissions_anchored_to_operational_content_type(self):
        ensure_role_groups()
        operational_ct = ContentType.objects.get_for_model(OperationalPermission)
        rows = Permission.objects.filter(codename__in=OPERATIONAL_PERMISSIONS)
        self.assertEqual(rows.count(), len(OPERATIONAL_PERMISSIONS))
        self.assertTrue(all(row.content_type_id == operational_ct.id for row in rows))

    def test_idempotent(self):
        ensure_role_groups()
        ensure_role_groups()
        ensure_role_groups()
        self.assertEqual(
            Permission.objects.filter(codename__in=OPERATIONAL_PERMISSIONS).count(),
            len(OPERATIONAL_PERMISSIONS),
        )
        for role, codenames in ROLE_PERMISSIONS.items():
            self.assertEqual(self._codenames(role), codenames)

    def test_prunes_stale_operational_permission(self):
        ensure_role_groups()
        operational_ct = ContentType.objects.get_for_model(OperationalPermission)
        Permission.objects.create(
            content_type=operational_ct, codename="obsolete.thing", name="Obsolete"
        )
        ensure_role_groups()
        self.assertFalse(Permission.objects.filter(codename="obsolete.thing").exists())

    def test_role_change_syncs_group(self):
        ensure_role_groups()
        cashier = Group.objects.get(name="Cashier")
        cashier.permissions.remove(Permission.objects.get(codename="pos"))
        self.assertNotIn("pos", self._codenames("Cashier"))
        ensure_role_groups()
        self.assertIn("pos", self._codenames("Cashier"))
        # Unmanaged extras on a group are left alone.
        self.assertEqual(self._codenames("Admin"), set(OPERATIONAL_PERMISSIONS))
