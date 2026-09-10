import {
  BarChart3,
  Bell,
  Boxes,
  LayoutDashboard,
  Package,
  ScanLine,
  Settings,
  ShoppingCart,
  Truck,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  /** Operational permission that gates this item (informational for now). */
  permission?: string;
}

export interface NavGroup {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

/** Primary navigation, mirroring HEXAGARE_FEATURES.md section 56. */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Dashboard",
    icon: LayoutDashboard,
    items: [{ label: "Overview", to: "/" }],
  },
  {
    label: "Products",
    icon: Package,
    items: [
      { label: "Products", to: "/products", permission: "products.view" },
      { label: "Categories", to: "/products/categories", permission: "products.view" },
      { label: "Product Units", to: "/products/units", permission: "serials.view" },
      { label: "Bulk Generate", to: "/products/bulk-generate", permission: "serials.manage" },
    ],
  },
  {
    label: "Inventory",
    icon: Boxes,
    items: [
      { label: "Overview", to: "/inventory", permission: "inventory.view" },
      { label: "Transfers", to: "/inventory/transfers", permission: "inventory.transfer" },
      { label: "Stock Ledger", to: "/inventory/ledger", permission: "inventory.view" },
      { label: "Alerts", to: "/inventory/alerts", permission: "inventory.view" },
    ],
  },
  {
    label: "Sales",
    icon: ShoppingCart,
    items: [
      { label: "New Bill", to: "/sales/new", permission: "pos" },
      { label: "Orders", to: "/sales/orders", permission: "sales.view" },
      { label: "Returns", to: "/sales/returns", permission: "returns" },
      { label: "Invoices", to: "/sales/invoices", permission: "billing.view" },
    ],
  },
  {
    label: "Barcode",
    icon: ScanLine,
    items: [{ label: "Scan", to: "/barcode/scan", permission: "barcode.scan" }],
  },
  {
    label: "Purchases",
    icon: Truck,
    items: [
      { label: "Suppliers", to: "/purchases/suppliers", permission: "purchases.view" },
      { label: "Purchase Orders", to: "/purchases/orders", permission: "purchases.view" },
      { label: "Receive Stock", to: "/purchases/receive", permission: "purchases_receiving" },
    ],
  },
  {
    label: "Customers",
    icon: Users,
    items: [{ label: "Customers", to: "/customers", permission: "customers.view" }],
  },
  {
    label: "Finance",
    icon: Wallet,
    items: [
      { label: "Payments", to: "/finance/payments", permission: "billing.view" },
      { label: "Expenses", to: "/finance/expenses", permission: "expenses.manage" },
      { label: "Profit", to: "/finance/profit", permission: "finance.view" },
    ],
  },
  {
    label: "Reports",
    icon: BarChart3,
    items: [{ label: "Reports", to: "/reports", permission: "reports.view" }],
  },
  {
    label: "Notifications",
    icon: Bell,
    items: [{ label: "Notifications", to: "/notifications" }],
  },
  {
    label: "Settings",
    icon: Settings,
    items: [
      { label: "General", to: "/settings", permission: "settings.manage" },
      { label: "Users", to: "/settings/users", permission: "users.manage" },
      { label: "Roles & Permissions", to: "/settings/roles", permission: "users.manage" },
    ],
  },
];
