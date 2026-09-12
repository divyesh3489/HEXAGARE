import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChannelComparisonChart } from "./channel-comparison-chart";
import { money } from "./format";
import { useDashboardAnalytics } from "./hooks";
import { SalesTrendChart } from "./sales-trend-chart";
import type { DashboardTopSellingRow } from "./types";

function ListCard<T>({
  title,
  rows,
  empty,
  renderRow,
}: {
  title: string;
  rows: T[];
  empty: string;
  renderRow: (row: T, i: number) => ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="divide-y">{rows.map(renderRow)}</ul>
        )}
      </CardContent>
    </Card>
  );
}

function TopSellingCard({ title, rows }: { title: string; rows: DashboardTopSellingRow[] }) {
  return (
    <ListCard
      title={title}
      rows={rows}
      empty="No sales in the last 30 days."
      renderRow={(row) => (
        <li key={row.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
          <span className="truncate pr-2">{row.name}</span>
          <span className="shrink-0 text-muted-foreground">{row.units_sold} units</span>
        </li>
      )}
    />
  );
}

export function AnalyticsSection() {
  const { data, isPending, error } = useDashboardAnalytics();

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Analytics</h2>
      {error && <p className="text-sm text-destructive">Couldn’t load analytics.</p>}
      {isPending && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Sales trend (last 30 days)</CardTitle>
              </CardHeader>
              <CardContent>
                <SalesTrendChart data={data.sales_graph} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Amazon vs Offline</CardTitle>
              </CardHeader>
              <CardContent>
                <ChannelComparisonChart data={data.sales_graph} />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <TopSellingCard title="Top-selling products" rows={data.top_selling_products} />
            <TopSellingCard title="Top-selling SKUs" rows={data.top_selling_skus} />
            <ListCard
              title="Low-stock products"
              rows={data.low_stock_products}
              empty="Nothing low on stock."
              renderRow={(row) => (
                <li
                  key={row.sku}
                  className="flex items-center justify-between px-4 py-2.5 text-sm"
                >
                  <span className="truncate pr-2">{row.product_name}</span>
                  <Badge variant={row.type === "out_of_stock" ? "destructive" : "outline"}>
                    {row.available} left
                  </Badge>
                </li>
              )}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ListCard
              title="Recent orders"
              rows={data.recent_orders}
              empty="No orders yet."
              renderRow={(row) => (
                <li key={row.id} className="px-4 py-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span>#{row.id}</span>
                    <span className="font-medium">{money(row.grand_total)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {row.channel} · {row.customer_name ?? "Walk-in"}
                  </p>
                </li>
              )}
            />
            <ListCard
              title="Recent returns"
              rows={data.recent_returns}
              empty="No returns yet."
              renderRow={(row) => (
                <li key={row.id} className="px-4 py-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span>Sale #{row.sale_id}</span>
                    <span className="font-medium">{money(row.refund_total)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{row.reason}</p>
                </li>
              )}
            />
            <ListCard
              title="Recent stock movements"
              rows={data.recent_stock_movements}
              empty="No stock movements yet."
              renderRow={(row) => (
                <li key={row.id} className="px-4 py-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="truncate pr-2">{row.sku}</span>
                    <span className="font-medium">
                      {row.quantity > 0 ? "+" : ""}
                      {row.quantity}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {row.kind} · {row.location}
                  </p>
                </li>
              )}
            />
          </div>
        </div>
      )}
    </section>
  );
}
