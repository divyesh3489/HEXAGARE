import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { ProtectedRoute } from "@/components/protected-route";
import { SerializedUnitsPanel } from "@/features/serialized-units";
import { DashboardPage } from "./dashboard";
import { LoginPage } from "./login";
import { StubPage } from "./stub-page";

const stubRoutes: { path: string; title: string; phase: string }[] = [
  { path: "products", title: "Products", phase: "Phase 2" },
  { path: "products/units", title: "Product Units", phase: "Phase 3" },
  { path: "products/bulk-generate", title: "Bulk Generate Units", phase: "Phase 5" },
  { path: "inventory", title: "Inventory Overview", phase: "Phase 4" },
  { path: "inventory/transfers", title: "Stock Transfers", phase: "Phase 4" },
  { path: "inventory/ledger", title: "Stock Ledger", phase: "Phase 4" },
  { path: "inventory/alerts", title: "Inventory Alerts", phase: "Phase 4" },
  { path: "sales/new", title: "New Bill", phase: "Phase 8" },
  { path: "sales/orders", title: "Orders", phase: "Phase 7" },
  { path: "sales/returns", title: "Returns", phase: "Phase 10" },
  { path: "sales/invoices", title: "Invoices", phase: "Phase 8" },
  { path: "barcode/scan", title: "Barcode Scanner", phase: "Phase 6" },
  { path: "purchases/suppliers", title: "Suppliers", phase: "Phase 12" },
  { path: "purchases/orders", title: "Purchase Orders", phase: "Phase 12" },
  { path: "purchases/receive", title: "Receive Stock", phase: "Phase 12" },
  { path: "customers", title: "Customers", phase: "Phase 11" },
  { path: "finance/payments", title: "Payments", phase: "Phase 8" },
  { path: "finance/expenses", title: "Expenses", phase: "Phase 13" },
  { path: "finance/profit", title: "Profit", phase: "Phase 13" },
  { path: "reports", title: "Reports", phase: "Phase 14" },
  { path: "notifications", title: "Notifications", phase: "Phase 15" },
  { path: "settings", title: "General Settings", phase: "Phase 17" },
  { path: "settings/users", title: "Users", phase: "Phase 17" },
  { path: "settings/roles", title: "Roles & Permissions", phase: "Phase 17" },
];

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "products/serial-numbers", element: <SerializedUnitsPanel /> },
          ...stubRoutes.map((route) => ({
            path: route.path,
            element: <StubPage title={route.title} phase={route.phase} />,
          })),
          {
            path: "*",
            element: <StubPage title="Not found" phase="a future phase" />,
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
