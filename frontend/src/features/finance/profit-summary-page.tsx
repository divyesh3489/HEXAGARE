import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useFinanceByChannel, useFinanceSummary } from "./hooks";
import type { FinanceSummary } from "./types";

/** `YYYY-MM-DD` in the viewer's local calendar -- `toISOString()` converts
 * through UTC first, which silently shifts the date near midnight in any
 * timezone ahead of UTC. */
function localDateString(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function firstOfMonth(): string {
  const now = new Date();
  return localDateString(new Date(now.getFullYear(), now.getMonth(), 1));
}

function today(): string {
  return localDateString(new Date());
}

function money(value: string): string {
  const n = Number(value);
  return Number.isNaN(n) ? value : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function Tile({ label, value, emphasize }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <Card>
      <CardContent className="py-4">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className={emphasize ? "text-xl font-semibold" : "text-lg font-semibold"}>{value}</p>
      </CardContent>
    </Card>
  );
}

export function ProfitSummaryPage() {
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());

  const validRange = Boolean(dateFrom && dateTo && dateFrom <= dateTo);
  const query = { date_from: dateFrom, date_to: dateTo };
  const { data: summary, isPending, error } = useFinanceSummary(query, validRange);
  const { data: byChannel } = useFinanceByChannel(query, validRange);

  return (
    <div>
      <PageHeader
        title="Profit"
        description="Sales revenue minus product cost, packaging, shipping, Amazon fees, advertising and other expenses."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>From</Label>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>To</Label>
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>

      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && <p className="text-sm text-destructive">Couldn’t load the profit summary.</p>}
      {isPending && validRange && <p className="text-sm text-muted-foreground">Loading…</p>}

      {summary && (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Tile label="Gross sales (incl. GST)" value={money(summary.gross_sales)} />
            <Tile label="Taxable sales" value={money(summary.taxable_sales)} />
            <Tile label="GST collected" value={money(summary.gst_collected)} />
            <Tile label="Discounts" value={money(summary.discounts)} />
            <Tile label="Refunds" value={money(summary.refunds)} />
            <Tile label="Product cost" value={money(summary.product_cost)} />
            <Tile label="Amazon fees" value={money(summary.amazon_fees)} />
            <Tile label="Shipping" value={money(summary.shipping)} />
            <Tile label="Advertising" value={money(summary.advertising)} />
            <Tile label="Packaging" value={money(summary.packaging)} />
            <Tile label="Other expenses" value={money(summary.other_expenses)} />
          </div>

          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            <Tile label="Gross profit" value={money(summary.gross_profit)} emphasize />
            <Tile label="Net profit" value={money(summary.net_profit)} emphasize />
            <Tile label="Profit margin" value={`${Number(summary.profit_margin).toFixed(2)}%`} emphasize />
          </div>
        </>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">By channel</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Channel</th>
                  <th className="px-4 py-3 text-right font-medium">Taxable sales</th>
                  <th className="px-4 py-3 text-right font-medium">Product cost</th>
                  <th className="px-4 py-3 text-right font-medium">Net profit</th>
                  <th className="px-4 py-3 text-right font-medium">Margin</th>
                </tr>
              </thead>
              <tbody>
                {!byChannel && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {byChannel?.map((row: FinanceSummary) => (
                  <tr key={row.channel} className="border-b last:border-0">
                    <td className="px-4 py-3 font-medium">{row.channel}</td>
                    <td className="px-4 py-3 text-right">{money(row.taxable_sales)}</td>
                    <td className="px-4 py-3 text-right">{money(row.product_cost)}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(row.net_profit)}</td>
                    <td className="px-4 py-3 text-right">
                      {Number(row.profit_margin).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
