import { lazy, Suspense, useEffect, useState } from "react";
import { ScanLine } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { ScanFrame, ScanFrameMarks } from "@/components/scan-frame";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAllCategories } from "@/features/products/hooks";
import { useSalesChannels } from "@/features/sales/hooks";
import { useLocations } from "@/features/serialized-units/hooks";
import { cn } from "@/lib/utils";
import type { ReportQuery } from "./api";
import {
  useCreateReportExport,
  useDownloadReportExport,
  useFinancialReport,
  useInventoryReport,
  useProductsReport,
  useReportExportStatus,
  useSalesReport,
  useSerialNumberHistoryReport,
  useSerialNumbersReport,
} from "./hooks";
import type { ExportFormat, ReportType } from "./types";

// Same code-split reasoning as New Bill / New Return (ADR-011) -- ZXing stays
// out of the Reports chunk until the scanner is opened.
const CameraScanPanel = lazy(() =>
  import("@/features/sales/camera-scan-panel").then((m) => ({ default: m.CameraScanPanel })),
);

const selectClass =
  "h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm";

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

/** `YYYY-MM-DD` in the viewer's local calendar -- see
 * `features/finance/profit-summary-page.tsx` for why not `toISOString()`. */
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

function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  }
  return String(value);
}

/* ----------------------------------------------------------------- Shared UI */

function DateRangeFields({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
}) {
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label>From</Label>
        <Input type="date" value={from} onChange={(e) => onFrom(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>To</Label>
        <Input type="date" value={to} onChange={(e) => onTo(e.target.value)} />
      </div>
    </>
  );
}

function ChannelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: channels } = useSalesChannels();
  return (
    <div className="flex flex-col gap-1.5">
      <Label>Channel</Label>
      <select className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All channels</option>
        {(channels?.data ?? []).map((ch) => (
          <option key={ch.code} value={ch.code}>
            {ch.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function LocationSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: locations } = useLocations();
  return (
    <div className="flex flex-col gap-1.5">
      <Label>Location</Label>
      <select className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All locations</option>
        {(locations?.data ?? []).map((loc) => (
          <option key={loc.code} value={loc.code}>
            {loc.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function CategorySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: categories } = useAllCategories();
  return (
    <div className="flex flex-col gap-1.5">
      <Label>Category</Label>
      <select className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All categories</option>
        {(categories?.data ?? []).map((cat) => (
          <option key={cat.id} value={cat.id}>
            {cat.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function SummaryTiles({ summary }: { summary: Record<string, unknown> }) {
  const entries = Object.entries(summary).filter(([, v]) => typeof v !== "object" || v === null);
  if (!entries.length) return null;
  return (
    <div className="mb-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {entries.map(([key, value]) => (
        <Card key={key}>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              {humanize(key)}
            </p>
            <p className="text-lg font-semibold">{formatCell(value)}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No rows for this range.
      </p>
    );
  }
  const columns = Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-4 py-3 font-medium">
                {humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b last:border-0">
              {columns.map((c) => (
                <td key={c} className="whitespace-nowrap px-4 py-2">
                  {formatCell(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExportMenu({
  reportType,
  filters,
  filenameBase,
}: {
  reportType: ReportType;
  filters: Record<string, unknown>;
  filenameBase: string;
}) {
  const [pendingId, setPendingId] = useState<number | undefined>(undefined);
  const [pendingFormat, setPendingFormat] = useState<ExportFormat>("CSV");
  const createExport = useCreateReportExport();
  const download = useDownloadReportExport();
  const { data: job } = useReportExportStatus(pendingId);

  useEffect(() => {
    if (!job || pendingId === undefined) return;
    if (job.status === "READY") {
      const ext = pendingFormat === "XLSX" ? "xlsx" : "csv";
      download.mutate({ id: pendingId, filename: `${filenameBase}.${ext}` });
      toast.success("Export ready — download started");
      setPendingId(undefined);
    } else if (job.status === "FAILED") {
      toast.error(job.error_message || "Export failed");
      setPendingId(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per status transition, not on every re-render
  }, [job?.status]);

  const busy = pendingId !== undefined;

  const runExport = (export_format: ExportFormat) => {
    setPendingFormat(export_format);
    createExport.mutate(
      { report_type: reportType, export_format, filters },
      {
        onSuccess: (job) => setPendingId(job.id),
        onError: (err) => toast.error(errMsg(err, "Couldn't start the export")),
      },
    );
  };

  if (busy) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-slate-950 px-3 py-1.5 text-white">
        <ScanFrameMarks size="sm" />
        <span className="text-xs text-white/70">Exporting…</span>
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => runExport("CSV")}>CSV</DropdownMenuItem>
        <DropdownMenuItem onClick={() => runExport("XLSX")}>Excel</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* ----------------------------------------------------------------------- Tabs */

function SalesTab() {
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());
  const [channel, setChannel] = useState("");
  const [groupBy, setGroupBy] = useState("");

  const validRange = Boolean(dateFrom && dateTo && dateFrom <= dateTo);
  const query: ReportQuery = {
    date_from: dateFrom,
    date_to: dateTo,
    channel: channel || undefined,
    group_by: groupBy || undefined,
  };
  const { data, isPending, error } = useSalesReport(query, validRange);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <DateRangeFields from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        <ChannelSelect value={channel} onChange={setChannel} />
        <div className="flex flex-col gap-1.5">
          <Label>Group by</Label>
          <select
            className={selectClass}
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
          >
            <option value="">Summary only</option>
            <option value="product">Product</option>
            <option value="variant">Variant / SKU</option>
            <option value="category">Category</option>
            <option value="serial">Serial number</option>
          </select>
        </div>
        {data && <ExportMenu reportType="SALES" filters={query} filenameBase="sales-report" />}
      </div>
      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && <p className="text-sm text-destructive">{errMsg(error, "Couldn't load the sales report.")}</p>}
      {isPending && validRange && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={data.rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function InventoryTab() {
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState("");
  const [view, setView] = useState<"balance" | "movement">("balance");
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());

  const needsDateRange = view === "movement";
  const validRange = !needsDateRange || Boolean(dateFrom && dateTo && dateFrom <= dateTo);
  const query: ReportQuery = {
    location: location || undefined,
    category: category || undefined,
    view,
    ...(needsDateRange ? { date_from: dateFrom, date_to: dateTo } : {}),
  };
  const { data, isPending, error } = useInventoryReport(query, validRange);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>View</Label>
          <select
            className={selectClass}
            value={view}
            onChange={(e) => setView(e.target.value as "balance" | "movement")}
          >
            <option value="balance">Current stock</option>
            <option value="movement">Stock movement</option>
          </select>
        </div>
        <LocationSelect value={location} onChange={setLocation} />
        {view === "balance" && <CategorySelect value={category} onChange={setCategory} />}
        {needsDateRange && (
          <DateRangeFields from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        )}
        {data && (
          <ExportMenu
            reportType="INVENTORY"
            filters={query}
            filenameBase={view === "movement" ? "inventory-movement" : "inventory-stock"}
          />
        )}
      </div>
      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && (
        <p className="text-sm text-destructive">{errMsg(error, "Couldn't load the inventory report.")}</p>
      )}
      {isPending && validRange && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={data.rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function SerialNumbersTab() {
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const validRange = !(dateFrom && dateTo) || dateFrom <= dateTo;
  const query: ReportQuery = {
    location: location || undefined,
    category: category || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const { data, isPending, error } = useSerialNumbersReport(query, validRange);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <LocationSelect value={location} onChange={setLocation} />
        <CategorySelect value={category} onChange={setCategory} />
        <DateRangeFields from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        {data && (
          <ExportMenu
            reportType="SERIAL_NUMBERS"
            filters={query}
            filenameBase="serial-numbers"
          />
        )}
      </div>
      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && (
        <p className="text-sm text-destructive">
          {errMsg(error, "Couldn't load the serial numbers report.")}
        </p>
      )}
      {isPending && validRange && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={data.rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function SerialNumberHistoryTab() {
  const [serial, setSerial] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [scanning, setScanning] = useState(false);
  const query: ReportQuery = { serial_number: submitted };
  const { data, isPending, error } = useSerialNumberHistoryReport(query, Boolean(submitted));

  const lookup = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSerial(trimmed);
    setSubmitted(trimmed);
  };

  return (
    <div>
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          lookup(serial);
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label>Serial number</Label>
          <Input
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="HXMP1123-000001"
          />
        </div>
        <Button type="submit">Look up</Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => setScanning((s) => !s)}
          aria-label="Scan with camera"
        >
          <ScanLine />
        </Button>
        {data && (
          <ExportMenu
            reportType="SERIAL_NUMBER_HISTORY"
            filters={query}
            filenameBase={`serial-history-${submitted}`}
          />
        )}
      </form>
      {scanning && (
        <div className="mb-4 max-w-md">
          <Suspense fallback={<Skeleton className="aspect-video w-full" />}>
            <CameraScanPanel onAdd={lookup} onClose={() => setScanning(false)} />
          </Suspense>
        </div>
      )}
      {error && (
        <p className="text-sm text-destructive">
          {errMsg(error, "Couldn't find that serial number.")}
        </p>
      )}
      {isPending && submitted && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={data.rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function ProductsTab() {
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());
  const [channel, setChannel] = useState("");
  const [worstFirst, setWorstFirst] = useState(false);

  const validRange = Boolean(dateFrom && dateTo && dateFrom <= dateTo);
  const query: ReportQuery = {
    date_from: dateFrom,
    date_to: dateTo,
    channel: channel || undefined,
  };
  const { data, isPending, error } = useProductsReport(query, validRange);
  const rows = data ? (worstFirst ? [...data.rows].reverse() : data.rows) : [];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <DateRangeFields from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        <ChannelSelect value={channel} onChange={setChannel} />
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={worstFirst}
            onChange={(e) => setWorstFirst(e.target.checked)}
          />
          Worst-selling first
        </label>
        {data && <ExportMenu reportType="PRODUCTS" filters={query} filenameBase="products-report" />}
      </div>
      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && (
        <p className="text-sm text-destructive">{errMsg(error, "Couldn't load the products report.")}</p>
      )}
      {isPending && validRange && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function FinancialTab() {
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());
  const [channel, setChannel] = useState("");

  const validRange = Boolean(dateFrom && dateTo && dateFrom <= dateTo);
  const query: ReportQuery = {
    date_from: dateFrom,
    date_to: dateTo,
    channel: channel || undefined,
  };
  const { data, isPending, error } = useFinancialReport(query, validRange);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <DateRangeFields from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        <ChannelSelect value={channel} onChange={setChannel} />
        {data && (
          <ExportMenu reportType="FINANCIAL" filters={query} filenameBase="financial-report" />
        )}
      </div>
      {!validRange && (
        <p className="text-sm text-destructive">The start date must not be after the end date.</p>
      )}
      {error && (
        <p className="text-sm text-destructive">{errMsg(error, "Couldn't load the financial report.")}</p>
      )}
      {isPending && validRange && (
        <Card>
          <CardContent className="p-0">
            <ScanFrame message="Loading report…" className="rounded-md" />
          </CardContent>
        </Card>
      )}
      {data && (
        <>
          <SummaryTiles summary={data.summary} />
          <Card>
            <CardContent className="p-0">
              <RowsTable rows={data.rows} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- Page */

type TabKey =
  | "sales"
  | "inventory"
  | "serial-numbers"
  | "serial-number-history"
  | "products"
  | "financial";

const TABS: { key: TabKey; label: string }[] = [
  { key: "sales", label: "Sales" },
  { key: "inventory", label: "Inventory" },
  { key: "serial-numbers", label: "Serial Numbers" },
  { key: "serial-number-history", label: "Serial Number History" },
  { key: "products", label: "Products" },
  { key: "financial", label: "Financial" },
];

export function ReportsPage() {
  const [tab, setTab] = useState<TabKey>("sales");

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Sales, inventory, serial number, product and financial reports — filter and export to CSV or Excel."
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "sales" && <SalesTab />}
      {tab === "inventory" && <InventoryTab />}
      {tab === "serial-numbers" && <SerialNumbersTab />}
      {tab === "serial-number-history" && <SerialNumberHistoryTab />}
      {tab === "products" && <ProductsTab />}
      {tab === "financial" && <FinancialTab />}
    </div>
  );
}
