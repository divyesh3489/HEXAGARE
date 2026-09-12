import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useHasPermission } from "@/hooks/use-auth";
import { useBackups, useCreateBackup, useDownloadBackup } from "./hooks";
import type { BackupJob, BackupStatus } from "./types";

const statusVariant: Record<BackupStatus, "secondary" | "default" | "destructive"> = {
  PENDING: "secondary",
  RUNNING: "secondary",
  SUCCESS: "default",
  FAILED: "destructive",
};

function fileSize(bytes: number | null): string {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;
}

function filename(job: BackupJob): string {
  return `hexagare-backup-${job.id}-${job.created_at.slice(0, 10)}.dump`;
}

export function BackupsPage() {
  const canManage = useHasPermission()("settings.manage");
  const { data, isPending, error } = useBackups({ page_size: 50 });
  const create = useCreateBackup();
  const download = useDownloadBackup();

  const jobs = data?.data ?? [];

  const trigger = async () => {
    try {
      await create.mutateAsync();
    } catch (err) {
      // Surfaced via create.error below.
      void err;
    }
  };

  return (
    <div>
      <PageHeader
        title="Backups"
        description="Manual database backups (pg_dump). Restore isn't available from here -- ask an engineer."
        actions={
          canManage ? (
            <Button onClick={trigger} disabled={create.isPending}>
              {create.isPending ? "Starting…" : "Run backup now"}
            </Button>
          ) : undefined
        }
      />

      {create.isError && (
        <p className="mb-4 text-sm text-destructive">
          {create.error instanceof ApiError ? create.error.message : "Could not start a backup."}
        </p>
      )}

      {error && <p className="text-sm text-destructive">Couldn’t load backup history.</p>}

      {!error && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-medium">Started</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Size</th>
                    <th className="px-4 py-3 font-medium">Triggered by</th>
                    <th className="px-4 py-3 font-medium">Error</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {isPending && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                        Loading…
                      </td>
                    </tr>
                  )}
                  {!isPending && jobs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                        No backups yet.
                      </td>
                    </tr>
                  )}
                  {jobs.map((job) => (
                    <tr key={job.id} className="border-b last:border-0">
                      <td className="px-4 py-3 whitespace-nowrap">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={statusVariant[job.status]}>{job.status}</Badge>
                      </td>
                      <td className="px-4 py-3">{fileSize(job.file_size)}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {job.triggered_by_email ?? "—"}
                      </td>
                      <td className="px-4 py-3 max-w-xs truncate text-xs text-destructive">
                        {job.error_message || "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {job.status === "SUCCESS" && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={download.isPending}
                            onClick={() =>
                              download.mutate({ id: job.id, filename: filename(job) })
                            }
                          >
                            Download
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
