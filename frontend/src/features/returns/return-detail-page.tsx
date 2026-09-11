import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInspectReturnUnit, useReturn } from "./hooks";
import { conditionVariant } from "./status";

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

export function ReturnDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const returnId = Number(params.returnId);
  const valid = !Number.isNaN(returnId);

  const { data: ret, isPending, error } = useReturn(valid ? returnId : undefined);
  const inspect = useInspectReturnUnit(valid ? returnId : undefined);

  if (isPending) {
    return (
      <div>
        <PageHeader title="Return" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !ret) {
    return (
      <div>
        <PageHeader title="Return" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This return could not be loaded.
            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={() => navigate("/sales/returns")}>
                Back to returns
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const handleInspect = (returnUnitId: number, condition: "RESELLABLE" | "DAMAGED") => {
    inspect.mutate(
      { returnUnitId, condition },
      {
        onSuccess: () => toast.success("Unit inspected"),
        onError: (err) => toast.error(errMsg(err, "Couldn't record the inspection")),
      },
    );
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title={`Return #${ret.id}`}
        description={`From sale #${ret.sale} · ${ret.sale_detail.sales_channel_name}`}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/sales/returns")}>
            Back to returns
          </Button>
        }
      />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Reason</span>
            <span>{ret.reason}</span>
          </div>
          {ret.note && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Note</span>
              <span>{ret.note}</span>
            </div>
          )}
          <div className="flex justify-between border-t pt-1 font-semibold">
            <span>Refund total</span>
            <span>₹{ret.refund_total}</span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Created</span>
            <span>{new Date(ret.created_at).toLocaleString()}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Units</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2 font-medium">Product</th>
                  <th className="px-4 py-2 font-medium">Serial</th>
                  <th className="px-4 py-2 text-right font-medium">Refund</th>
                  <th className="px-4 py-2 font-medium">Condition</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {ret.units.map((unit) => (
                  <tr key={unit.id} className="border-b last:border-0">
                    <td className="px-4 py-2">
                      {unit.product_name}{" "}
                      <span className="font-mono text-xs text-muted-foreground">{unit.sku}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">{unit.serial_number}</td>
                    <td className="px-4 py-2 text-right">₹{unit.refund_amount}</td>
                    <td className="px-4 py-2">
                      <Badge variant={conditionVariant(unit.condition)}>{unit.condition}</Badge>
                    </td>
                    <td className="px-4 py-2 text-right">
                      {unit.condition === "PENDING" && (
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={inspect.isPending}
                            onClick={() => handleInspect(unit.id, "RESELLABLE")}
                          >
                            Mark resellable
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={inspect.isPending}
                            onClick={() => handleInspect(unit.id, "DAMAGED")}
                          >
                            Mark damaged
                          </Button>
                        </div>
                      )}
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
