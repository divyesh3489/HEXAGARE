import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { money } from "./format";
import { useDashboardSales } from "./hooks";
import { Tile } from "./tile";

function channelLabel(code: string): string {
  return code.charAt(0) + code.slice(1).toLowerCase();
}

export function SalesSection() {
  const { data, isPending, error } = useDashboardSales();

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Sales</h2>
      {error && <p className="text-sm text-destructive">Couldn’t load sales.</p>}
      {isPending && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Tile label="Total sales" value={money(data.total_sales)} emphasize />
            <Tile label="Today" value={money(data.today_sales)} />
            <Tile label="This week" value={money(data.weekly_sales)} />
            <Tile label="This month" value={money(data.monthly_sales)} />
            <Tile label="This year" value={money(data.yearly_sales)} />
            <Tile label="Total orders" value={String(data.total_orders)} />
            <Tile label="Products sold" value={String(data.products_sold)} />
            <Tile label="Units sold" value={String(data.units_sold)} />
          </div>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">By channel</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-6">
              {Object.entries(data.by_channel).map(([code, total]) => (
                <div key={code}>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">
                    {channelLabel(code)}
                  </p>
                  <p className="text-lg font-semibold">{money(total)}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
