import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useHasPermission } from "@/hooks/use-auth";
import { useSupplierMutations, useSuppliers } from "./hooks";
import type { SupplierWriteBody } from "./types";

const EMPTY: SupplierWriteBody = {
  name: "",
  company: "",
  phone: "",
  email: "",
  address: "",
  gstin: "",
  payment_terms: "",
  notes: "",
};

export function SuppliersPage() {
  const canManage = useHasPermission()("suppliers.manage");
  const [search, setSearch] = useState("");
  const { data, isPending, error } = useSuppliers({ search, page_size: 200 });
  const { create } = useSupplierMutations();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<SupplierWriteBody>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const suppliers = data?.data ?? [];

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
        setFormError(err instanceof Error ? err.message : "Could not save the supplier.");
      }
    }
  };

  return (
    <div>
      <PageHeader
        title="Suppliers"
        description="Vendors you purchase stock from, with purchase-order history."
        actions={
          canManage && !creating ? <Button onClick={startNew}>New supplier</Button> : undefined
        }
      />

      <div className="mb-4">
        <Input
          placeholder="Search by name, company, phone, email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {creating && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">New supplier</h3>
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
                <Label>Company</Label>
                <Input
                  value={draft.company}
                  onChange={(e) => setDraft((d) => ({ ...d, company: e.target.value }))}
                />
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
              <div className="flex flex-col gap-1.5">
                <Label>Payment terms</Label>
                <Input
                  value={draft.payment_terms}
                  placeholder="e.g. Net 30"
                  onChange={(e) => setDraft((d) => ({ ...d, payment_terms: e.target.value }))}
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

      {error && <p className="text-sm text-destructive">Couldn’t load suppliers.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Company</th>
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
                {!isPending && suppliers.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">
                      No suppliers yet.
                    </td>
                  </tr>
                )}
                {suppliers.map((s) => (
                  <tr key={s.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-medium">
                      <Link to={`/purchases/suppliers/${s.id}`} className="hover:underline">
                        {s.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{s.company || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{s.phone || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{s.email || "—"}</td>
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
