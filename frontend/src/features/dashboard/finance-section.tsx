import { money } from "./format";
import { useDashboardFinance } from "./hooks";
import { Tile } from "./tile";

export function FinanceSection() {
  const { data, isPending, error } = useDashboardFinance();

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Finance (this month)</h2>
      {error && <p className="text-sm text-destructive">Couldn’t load finance figures.</p>}
      {isPending && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && (
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <Tile label="Revenue" value={money(data.revenue)} emphasize />
          <Tile label="Taxable sales" value={money(data.taxable_sales)} />
          <Tile label="GST collected" value={money(data.gst_collected)} />
          <Tile label="Product cost" value={money(data.product_cost)} />
          <Tile label="Amazon fees" value={money(data.amazon_fees)} />
          <Tile label="Shipping" value={money(data.shipping)} />
          <Tile label="Advertising" value={money(data.advertising)} />
          <Tile label="Packaging" value={money(data.packaging)} />
          <Tile label="Other expenses" value={money(data.other_expenses)} />
          <Tile label="Gross profit" value={money(data.gross_profit)} emphasize />
          <Tile label="Net profit" value={money(data.net_profit)} emphasize />
          <Tile label="Profit margin" value={`${Number(data.profit_margin).toFixed(2)}%`} emphasize />
        </div>
      )}
    </section>
  );
}
