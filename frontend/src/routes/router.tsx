import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/page-header";
import { ProtectedRoute } from "@/components/protected-route";
import { Skeleton } from "@/components/ui/skeleton";
import { InvoiceDetailPage, InvoicesPage } from "@/features/billing";
import {
  BulkGeneratePage,
  LabelBatchDetailPage,
  LabelBatchesPage,
} from "@/features/bulk-generate";
import { CustomerDetailPage, CustomersPage } from "@/features/customers";
import { DashboardPage } from "@/features/dashboard";
import { ExpensesPage } from "@/features/expenses";
import { ProfitSummaryPage } from "@/features/finance";
import {
  InventoryAlertsPage,
  InventoryOverviewPage,
  StockLedgerPage,
  StockTransferDetailPage,
  StockTransferNewPage,
  StockTransfersPage,
} from "@/features/inventory";
import { CategoriesPage, ProductDetailPage, ProductsPage } from "@/features/products";
import {
  NewPurchaseOrderPage,
  PurchaseOrderDetailPage,
  PurchaseOrdersPage,
  ReceiveStockPage,
} from "@/features/purchases";
import { ReportsPage } from "@/features/reports";
import { NewReturnPage, ReturnDetailPage, ReturnsPage } from "@/features/returns";
import { NewBillPage, OrdersPage } from "@/features/sales";
import {
  AuditLogPage,
  BackupsPage,
  GeneralSettingsPage,
  RolesPage,
  UsersPage,
} from "@/features/settings";
import { SerializedUnitDetailPage, SerializedUnitsPanel } from "@/features/serialized-units";
import { SupplierDetailPage, SuppliersPage } from "@/features/suppliers";
import { LoginPage } from "./login";
import { StubPage } from "./stub-page";

// The scanner pulls in the ZXing decoder (~large); keep it off the main bundle.
const ScannerPage = lazy(() =>
  import("@/features/scanner").then((m) => ({ default: m.ScannerPage })),
);

// Most users never touch the Amazon integration -- keep it out of the main
// bundle, same ADR-011 code-split reasoning as the scanner.
const AmazonImportPage = lazy(() =>
  import("@/features/integrations").then((m) => ({ default: m.AmazonImportPage })),
);
const AmazonImportHistoryPage = lazy(() =>
  import("@/features/integrations").then((m) => ({ default: m.AmazonImportHistoryPage })),
);
const AmazonFeeSettingsPage = lazy(() =>
  import("@/features/integrations").then((m) => ({ default: m.AmazonFeeSettingsPage })),
);
const AmazonSkuMappingPage = lazy(() =>
  import("@/features/integrations").then((m) => ({ default: m.AmazonSkuMappingPage })),
);

const integrationsFallback = (
  <div className="mx-auto max-w-2xl">
    <PageHeader title="Amazon integration" />
    <Skeleton className="h-64 w-full" />
  </div>
);

const scannerFallback = (
  <div className="mx-auto max-w-md">
    <PageHeader title="Scan" />
    <Skeleton className="aspect-square w-full" />
  </div>
);

const stubRoutes: { path: string; title: string; phase: string }[] = [
  { path: "finance/payments", title: "Payments", phase: "Phase 8" },
  { path: "notifications", title: "Notifications", phase: "Phase 15" },
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
          { path: "products/bulk-generate", element: <BulkGeneratePage /> },
          { path: "products/bulk-generate/history", element: <LabelBatchesPage /> },
          { path: "products/bulk-generate/:batchId", element: <LabelBatchDetailPage /> },
          { path: "products/:productId", element: <ProductDetailPage /> },
          { path: "inventory", element: <InventoryOverviewPage /> },
          { path: "inventory/transfers", element: <StockTransfersPage /> },
          { path: "inventory/transfers/new", element: <StockTransferNewPage /> },
          { path: "inventory/transfers/:transferId", element: <StockTransferDetailPage /> },
          { path: "inventory/ledger", element: <StockLedgerPage /> },
          { path: "inventory/alerts", element: <InventoryAlertsPage /> },
          { path: "sales/orders", element: <OrdersPage /> },
          { path: "sales/new", element: <NewBillPage /> },
          { path: "sales/invoices", element: <InvoicesPage /> },
          { path: "sales/invoices/:invoiceId", element: <InvoiceDetailPage /> },
          { path: "sales/returns", element: <ReturnsPage /> },
          { path: "sales/returns/new", element: <NewReturnPage /> },
          { path: "sales/returns/:returnId", element: <ReturnDetailPage /> },
          { path: "customers", element: <CustomersPage /> },
          { path: "customers/:customerId", element: <CustomerDetailPage /> },
          { path: "finance/expenses", element: <ExpensesPage /> },
          { path: "finance/profit", element: <ProfitSummaryPage /> },
          { path: "purchases/suppliers", element: <SuppliersPage /> },
          { path: "purchases/suppliers/:supplierId", element: <SupplierDetailPage /> },
          { path: "purchases/orders", element: <PurchaseOrdersPage /> },
          { path: "purchases/orders/new", element: <NewPurchaseOrderPage /> },
          { path: "purchases/orders/:orderId", element: <PurchaseOrderDetailPage /> },
          { path: "purchases/receive", element: <ReceiveStockPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "settings", element: <GeneralSettingsPage /> },
          { path: "settings/users", element: <UsersPage /> },
          { path: "settings/roles", element: <RolesPage /> },
          { path: "settings/activity", element: <AuditLogPage /> },
          { path: "settings/backups", element: <BackupsPage /> },
          {
            path: "barcode/scan",
            element: (
              <Suspense fallback={scannerFallback}>
                <ScannerPage />
              </Suspense>
            ),
          },
          {
            path: "integrations/amazon/import",
            element: (
              <Suspense fallback={integrationsFallback}>
                <AmazonImportPage />
              </Suspense>
            ),
          },
          {
            path: "integrations/amazon/imports",
            element: (
              <Suspense fallback={integrationsFallback}>
                <AmazonImportHistoryPage />
              </Suspense>
            ),
          },
          {
            path: "integrations/amazon/fees",
            element: (
              <Suspense fallback={integrationsFallback}>
                <AmazonFeeSettingsPage />
              </Suspense>
            ),
          },
          {
            path: "integrations/amazon/sku-mapping",
            element: (
              <Suspense fallback={integrationsFallback}>
                <AmazonSkuMappingPage />
              </Suspense>
            ),
          },
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
