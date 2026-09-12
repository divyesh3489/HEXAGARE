export type ReportType =
  | "SALES"
  | "INVENTORY"
  | "SERIAL_NUMBERS"
  | "SERIAL_NUMBER_HISTORY"
  | "PRODUCTS"
  | "FINANCIAL";

export type ExportFormat = "CSV" | "XLSX";

/** Every `GET /reports/<type>/` endpoint returns this shape -- `summary` for
 * tiles, `rows` for the on-screen table (and what gets exported). Row/summary
 * fields vary by report and filters, so both are left loosely typed. */
export interface ReportResult {
  summary: Record<string, unknown>;
  rows: Record<string, unknown>[];
}

export interface ReportExport {
  id: number;
  report_type: ReportType;
  report_type_display: string;
  export_format: ExportFormat;
  filters: Record<string, unknown>;
  status: "PENDING" | "READY" | "FAILED";
  download_url: string | null;
  error_message: string;
  requested_by_email: string | null;
  created_at: string;
  completed_at: string | null;
}
