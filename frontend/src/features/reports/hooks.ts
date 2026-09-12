import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type ReportQuery, reportExportsApi, reportKeys, reportsApi } from "./api";

function useReport(
  key: readonly unknown[],
  queryFn: () => ReturnType<typeof reportsApi.sales>,
  enabled: boolean,
) {
  return useQuery({ queryKey: key, queryFn, enabled });
}

export function useSalesReport(query: ReportQuery, enabled: boolean) {
  return useReport(reportKeys.sales(query), () => reportsApi.sales(query), enabled);
}

export function useInventoryReport(query: ReportQuery, enabled: boolean) {
  return useReport(reportKeys.inventory(query), () => reportsApi.inventory(query), enabled);
}

export function useSerialNumbersReport(query: ReportQuery, enabled: boolean) {
  return useReport(
    reportKeys.serialNumbers(query),
    () => reportsApi.serialNumbers(query),
    enabled,
  );
}

export function useSerialNumberHistoryReport(query: ReportQuery, enabled: boolean) {
  return useReport(
    reportKeys.serialNumberHistory(query),
    () => reportsApi.serialNumberHistory(query),
    enabled,
  );
}

export function useProductsReport(query: ReportQuery, enabled: boolean) {
  return useReport(reportKeys.products(query), () => reportsApi.products(query), enabled);
}

export function useFinancialReport(query: ReportQuery, enabled: boolean) {
  return useReport(reportKeys.financial(query), () => reportsApi.financial(query), enabled);
}

export function useCreateReportExport() {
  return useMutation({ mutationFn: reportExportsApi.create });
}

/** Poll a just-created export every 1.5s until it leaves PENDING. */
export function useReportExportStatus(id: number | undefined) {
  return useQuery({
    queryKey: reportKeys.export(id ?? -1),
    queryFn: () => reportExportsApi.get(id as number),
    enabled: id !== undefined,
    refetchInterval: (query) => (query.state.data?.status === "PENDING" ? 1500 : false),
  });
}

/** Fetches the ready file and saves it via a throwaway anchor element -- the
 * simplest way to trigger a real browser download from a Blob. */
export function useDownloadReportExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, filename }: { id: number; filename: string }) => {
      const blob = await reportExportsApi.download(id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["reports", "export"] }),
  });
}
