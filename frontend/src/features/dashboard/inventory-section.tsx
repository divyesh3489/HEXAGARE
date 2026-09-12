import { useDashboardInventory } from "./hooks";
import { Tile } from "./tile";

export function InventorySection() {
  const { data, isPending, error } = useDashboardInventory();

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Inventory</h2>
      {error && <p className="text-sm text-destructive">Couldn’t load inventory.</p>}
      {isPending && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && (
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <Tile label="Total serialized units" value={String(data.total_serialized_units)} emphasize />
          <Tile label="Available" value={String(data.available_units)} />
          <Tile label="Reserved" value={String(data.reserved_units)} />
          <Tile label="In transit" value={String(data.in_transit_units)} />
          <Tile label="Sold" value={String(data.sold_units)} />
          <Tile label="Returned" value={String(data.returned_units)} />
          <Tile label="Damaged" value={String(data.damaged_units)} />
          <Tile label="Lost" value={String(data.lost_units)} />
          <Tile label="Low-stock products" value={String(data.low_stock_products)} />
          <Tile label="Out-of-stock products" value={String(data.out_of_stock_products)} />
          <Tile label="Overstock products" value={String(data.overstock_products)} />
        </div>
      )}
    </section>
  );
}
