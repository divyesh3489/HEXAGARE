import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { ProtectedRoute } from "@/components/protected-route";
import {
  InventoryAlertsPage,
  InventoryOverviewPage,
  StockLedgerPage,
  StockTransferDetailPage,
  StockTransferNewPage,
  StockTransfersPage,
} from "@/features/inventory";
import { CategoriesPage, ProductDetailPage, ProductsPage } from "@/features/products";
import { SerializedUnitDetailPage, SerializedUnitsPanel } from "@/features/serialized-units";
import { DashboardPage } from "./dashboard";
import { LoginPage } from "./login";
import { StubPage } from "./stub-page";

const stubRoutes: { path: string; title: string; phase: string }[] = [
  { path: "products/bulk-generate", title: "Bulk Generate Units", phase: "Phase 5" },
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
          { path: "products", element: <ProductsPage /> },
          { path: "products/categories", element: <CategoriesPage /> },
          { path: "products/units", element: <SerializedUnitsPanel /> },
          { path: "products/units/:unitId", element: <SerializedUnitDetailPage /> },
          { path: "products/:productId", element: <ProductDetailPage /> },
          { path: "inventory", element: <InventoryOverviewPage /> },
          { path: "inventory/transfers", element: <StockTransfersPage /> },
          { path: "inventory/transfers/new", element: <StockTransferNewPage /> },
          { path: "inventory/transfers/:transferId", element: <StockTransferDetailPage /> },
          { path: "inventory/ledger", element: <StockLedgerPage /> },
          { path: "inventory/alerts", element: <InventoryAlertsPage /> },
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
