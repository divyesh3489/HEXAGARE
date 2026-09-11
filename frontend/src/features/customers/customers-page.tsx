import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useHasPermission } from "@/hooks/use-auth";
import { useCustomerMutations, useCustomers } from "./hooks";
import type { CustomerType, CustomerWriteBody } from "./types";

const EMPTY: CustomerWriteBody = {
  name: "",
  phone: "",
  email: "",
  address: "",
  gstin: "",
  notes: "",
  type: "REGISTERED",
};

export function CustomersPage() {
  const canManage = useHasPermission()("customers.manage");
  const [search, setSearch] = useState("");
  const { data, isPending, error } = useCustomers({ search, page_size: 200 });
  const { create } = useCustomerMutations();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<CustomerWriteBody>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const customers = data?.data ?? [];

  const startNew = () => {
    setDraft(EMPTY);
    setCreating(true);
    setFormError(null);
    setFieldErrors({});
  };
  const cancel = () => {
    setCreating(false);
    setDraft(EMPTY);
  };

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    try {
      await create.mutateAsync(draft);
      cancel();
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save the customer.");
      }
    }
  };

  return (
    <div>
      <PageHeader
        title="Customers"
        description="Registered customers and walk-ins, with order and purchase history."
        actions={
          canManage && !creating ? <Button onClick={startNew}>New customer</Button> : undefined
        }
      />

      <div className="mb-4">
        <Input
          placeholder="Search by name, phone, email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {creating && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">New customer</h3>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
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
                    setDraft((d) => ({ ...d, type: e.target.value as CustomerType }))
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
                  onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Email</Label>
                <Input
                  type="email"
                  value={draft.email}
                  onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>GSTIN</Label>
                <Input
                  value={draft.gstin}
                  onChange={(e) => setDraft((d) => ({ ...d, gstin: e.target.value }))}
                  className="font-mono"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Address</Label>
              <Textarea
                value={draft.address}
                onChange={(e) => setDraft((d) => ({ ...d, address: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Notes</Label>
              <Textarea
                value={draft.notes}
                onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={create.isPending}>
                Save
              </Button>
              <Button variant="outline" onClick={cancel}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">Couldn’t load customers.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                </tr>
              </thead>
              <tbody>
                {isPending && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {!isPending && customers.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">
                      No customers yet.
                    </td>
                  </tr>
                )}
                {customers.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-medium">
                      <Link to={`/customers/${c.id}`} className="hover:underline">
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {c.type === "REGISTERED" ? (
                        <Badge>Registered</Badge>
                      ) : (
                        <Badge variant="muted">Walk-in</Badge>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{c.phone || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.email || "—"}</td>
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
