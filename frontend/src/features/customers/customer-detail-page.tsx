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
import { saleStatusVariant } from "@/features/sales/status";
import { useCustomer, useCustomerMutations } from "./hooks";
import type { CustomerType, CustomerWriteBody } from "./types";

function rupees(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN")}`;
}

export function CustomerDetailPage() {
  const { customerId } = useParams();
  const navigate = useNavigate();
  const canManage = useHasPermission()("customers.manage");
  const id = Number(customerId);

  const { data: customer, isPending, error } = useCustomer(id);
  const { update, remove } = useCustomerMutations();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CustomerWriteBody | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const startEdit = () => {
    if (!customer) return;
    setDraft({
      name: customer.name,
      phone: customer.phone,
      email: customer.email,
      address: customer.address,
      gstin: customer.gstin,
      notes: customer.notes,
      type: customer.type,
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
        setFormError(err instanceof Error ? err.message : "Could not save the customer.");
      }
    }
  };

  const handleDelete = () => {
    remove.mutate(id, {
      onSuccess: () => navigate("/customers"),
    });
  };

  if (isPending) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Customer" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Customer" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Couldn&apos;t load this customer.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={customer.name}
        description={customer.type === "REGISTERED" ? "Registered customer" : "Walk-in customer"}
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
                  if (confirm(`Delete customer "${customer.name}"?`)) handleDelete();
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
            <h3 className="font-medium">Edit customer</h3>
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
                <Label>Type</Label>
                <select
                  value={draft.type}
                  onChange={(e) =>
                    setDraft((d) => d && { ...d, type: e.target.value as CustomerType })
                  }
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                >
                  <option value="REGISTERED">Registered</option>
                  <option value="WALK_IN">Walk-in</option>
                </select>
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
              <p>{customer.phone || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Email</p>
              <p>{customer.email || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">GSTIN</p>
              <p className="font-mono">{customer.gstin || "—"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Address</p>
              <p>{customer.address || "—"}</p>
            </div>
            {customer.notes && (
              <div className="sm:col-span-2">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Notes</p>
                <p>{customer.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Total purchases
            </p>
            <p className="text-lg font-semibold">{rupees(customer.total_purchases)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Total refunds
            </p>
            <p className="text-lg font-semibold">{rupees(customer.total_refunds)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Outstanding</p>
            <p className="text-lg font-semibold">{rupees(customer.outstanding_amount)}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Order history</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {customer.sales.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              No orders yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Order #</th>
                    <th className="px-4 py-2 font-medium">Channel</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 text-right font-medium">Total</th>
                    <th className="px-4 py-2 text-right font-medium">Balance due</th>
                    <th className="px-4 py-2 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {customer.sales.map((sale) => (
                    <tr key={sale.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">
                        <Link to={`/sales/new?sale=${sale.id}`} className="hover:underline">
                          #{sale.id}
                        </Link>
                      </td>
                      <td className="px-4 py-2">{sale.sales_channel_name}</td>
                      <td className="px-4 py-2">
                        <Badge variant={saleStatusVariant(sale.status)}>{sale.status}</Badge>
                      </td>
                      <td className="px-4 py-2 text-right">{rupees(sale.grand_total)}</td>
                      <td className="px-4 py-2 text-right">{rupees(sale.balance_due)}</td>
                      <td className="px-4 py-2 whitespace-nowrap text-muted-foreground">
                        {new Date(sale.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Purchased serial numbers</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {customer.serial_numbers.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              No serialized units purchased yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Serial</th>
                    <th className="px-4 py-2 font-medium">Product</th>
                    <th className="px-4 py-2 font-medium">SKU</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {customer.serial_numbers.map((unit) => (
                    <tr key={unit.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">
                        <Link to={`/products/units/${unit.id}`} className="hover:underline">
                          {unit.serial_number}
                        </Link>
                      </td>
                      <td className="px-4 py-2">{unit.product_name}</td>
                      <td className="px-4 py-2 font-mono text-xs">{unit.sku}</td>
                      <td className="px-4 py-2">
                        <Badge variant="muted">{unit.status}</Badge>
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
