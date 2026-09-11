import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useHasPermission } from "@/hooks/use-auth";
import { purchaseOrderStatusVariant } from "@/features/purchases/status";
import { useSupplier, useSupplierMutations } from "./hooks";
import type { SupplierWriteBody } from "./types";

function rupees(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN")}`;
}

export function SupplierDetailPage() {
  const { supplierId } = useParams();
  const navigate = useNavigate();
  const canManage = useHasPermission()("suppliers.manage");
  const id = Number(supplierId);

  const { data: supplier, isPending, error } = useSupplier(id);
  const { update, remove } = useSupplierMutations();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SupplierWriteBody | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const startEdit = () => {
    if (!supplier) return;
    setDraft({
      name: supplier.name,
      company: supplier.company,
      phone: supplier.phone,
      email: supplier.email,
      address: supplier.address,
      gstin: supplier.gstin,
      payment_terms: supplier.payment_terms,
      notes: supplier.notes,
    });
    setEditing(true);
    setFormError(null);
    setFieldErrors({});
  };

  const submit = async () => {
    if (!draft) return;
    setFormError(null);
    setFieldErrors({});
    try {
      await update.mutateAsync({ id, body: draft });
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save the supplier.");
      }
    }
  };

  const handleDelete = () => {
    remove.mutate(id, {
      onSuccess: () => navigate("/purchases/suppliers"),
    });
  };

  if (isPending) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Supplier" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !supplier) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Supplier" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Couldn&apos;t load this supplier.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={supplier.name}
        description={supplier.company || "Supplier"}
        actions={
          canManage && !editing ? (
            <div className="flex gap-2">
              <Button variant="outline" onClick={startEdit}>
                Edit
              </Button>
              <Button
                variant="outline"
                disabled={remove.isPending}
                onClick={() => {
                  if (confirm(`Delete supplier "${supplier.name}"?`)) handleDelete();
                }}
              >
                Delete
              </Button>
            </div>
          ) : undefined
        }
      />

      {editing && draft && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">Edit supplier</h3>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft((d) => d && { ...d, name: e.target.value })}
                />
                {fieldErrors.name && (
                  <p className="text-xs text-destructive">{fieldErrors.name.join(" ")}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Company</Label>
                <Input
                  value={draft.company}
                  onChange={(e) => setDraft((d) => d && { ...d, company: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Phone</Label>
                <Input
                  value={draft.phone}
                  onChange={(e) => setDraft((d) => d && { ...d, phone: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Email</Label>
                <Input
                  type="email"
                  value={draft.email}
                  onChange={(e) => setDraft((d) => d && { ...d, email: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>GSTIN</Label>
                <Input
                  value={draft.gstin}
                  onChange={(e) => setDraft((d) => d && { ...d, gstin: e.target.value })}
                  className="font-mono"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Payment terms</Label>
                <Input
                  value={draft.payment_terms}
                  onChange={(e) => setDraft((d) => d && { ...d, payment_terms: e.target.value })}
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Address</Label>
              <Textarea
                value={draft.address}
                onChange={(e) => setDraft((d) => d && { ...d, address: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Notes</Label>
              <Textarea
                value={draft.notes}
                onChange={(e) => setDraft((d) => d && { ...d, notes: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={update.isPending}>
                Save
              </Button>
              <Button variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {!editing && (
        <Card className="mb-4">
          <CardContent className="grid gap-3 py-5 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Phone</p>
              <p>{supplier.phone || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Email</p>
              <p>{supplier.email || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">GSTIN</p>
              <p className="font-mono">{supplier.gstin || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                Payment terms
              </p>
              <p>{supplier.payment_terms || "—"}</p>
            </div>
            <div className="sm:col-span-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Address</p>
              <p>{supplier.address || "—"}</p>
            </div>
            {supplier.notes && (
              <div className="sm:col-span-2">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Notes</p>
                <p>{supplier.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Total purchase value
            </p>
            <p className="text-lg font-semibold">{rupees(supplier.total_purchase_value)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Total paid</p>
            <p className="text-lg font-semibold">{rupees(supplier.total_paid)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Outstanding</p>
            <p className="text-lg font-semibold">{rupees(supplier.outstanding_amount)}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Purchase order history</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.orders.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              No purchase orders yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Order #</th>
                    <th className="px-4 py-2 font-medium">Reference</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 text-right font-medium">Total</th>
                    <th className="px-4 py-2 text-right font-medium">Balance due</th>
                    <th className="px-4 py-2 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {supplier.orders.map((order) => (
                    <tr key={order.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">
                        <Link to={`/purchases/orders/${order.id}`} className="hover:underline">
                          #{order.id}
                        </Link>
                      </td>
                      <td className="px-4 py-2">{order.reference || "—"}</td>
                      <td className="px-4 py-2">
                        <Badge variant={purchaseOrderStatusVariant(order.status)}>
                          {order.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right">{rupees(order.grand_total)}</td>
                      <td className="px-4 py-2 text-right">{rupees(order.balance_due)}</td>
                      <td className="px-4 py-2 whitespace-nowrap text-muted-foreground">
                        {new Date(order.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
