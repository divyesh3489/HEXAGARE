import { useState } from "react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useHasPermission } from "@/hooks/use-auth";
import { useBusinessSettings, useUpdateBusinessSettings } from "./hooks";
import type { BusinessSettings, BusinessSettingsWriteBody } from "./types";

function emptyDraft(s: BusinessSettings | undefined): BusinessSettingsWriteBody {
  return {
    business_name: s?.business_name ?? "",
    address: s?.address ?? "",
    phone: s?.phone ?? "",
    email: s?.email ?? "",
    gstin: s?.gstin ?? "",
    currency: s?.currency ?? "INR",
    default_tax_rate: s?.default_tax_rate ?? "",
    sku_prefix: s?.sku_prefix ?? "",
    serial_prefix: s?.serial_prefix ?? "",
    serial_padding: s?.serial_padding ?? "",
    invoice_prefix: s?.invoice_prefix ?? "",
    invoice_padding: s?.invoice_padding ?? "",
  };
}

export function GeneralSettingsPage() {
  const canManage = useHasPermission()("settings.manage");
  const { data, isPending, error } = useBusinessSettings();
  const update = useUpdateBusinessSettings();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<BusinessSettingsWriteBody>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const startEdit = () => {
    setDraft(emptyDraft(data));
    setEditing(true);
    setFormError(null);
    setFieldErrors({});
  };

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    try {
      await update.mutateAsync({
        ...draft,
        default_tax_rate: draft.default_tax_rate || null,
        serial_padding: draft.serial_padding || null,
        invoice_padding: draft.invoice_padding || null,
      });
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save settings.");
      }
    }
  };

  if (isPending) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Business Settings" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Business Settings" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Couldn&apos;t load business settings.
          </CardContent>
        </Card>
      </div>
    );
  }

  const row = (label: string, value: string | number | null) => (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="text-sm">{value || value === 0 ? value : "—"}</span>
    </div>
  );

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Business Settings"
        description="Business info, tax defaults, and SKU / serial / invoice numbering."
        actions={
          canManage && !editing ? <Button onClick={startEdit}>Edit</Button> : undefined
        }
      />

      {formError && <p className="mb-4 text-sm text-destructive">{formError}</p>}

      {!editing && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Business info</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              {row("Business name", data.business_name)}
              {row("GSTIN", data.gstin)}
              {row("Phone", data.phone)}
              {row("Email", data.email)}
              <div className="sm:col-span-2">{row("Address", data.address)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tax & numbering</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              {row("Currency", data.currency)}
              {row("Default GST rate (%)", data.default_tax_rate)}
              {row("SKU prefix", data.sku_prefix || "HEX (default)")}
              {row("Serial prefix", data.serial_prefix || "HX (default)")}
              {row("Serial padding", data.serial_padding ?? "6 (default)")}
              {row("Invoice prefix", data.invoice_prefix || "HEX-INV (default)")}
              {row("Invoice padding", data.invoice_padding ?? "6 (default)")}
            </CardContent>
          </Card>
          <p className="text-xs text-muted-foreground">
            Last updated {new Date(data.updated_at).toLocaleString()}
            {data.updated_by ? ` by ${data.updated_by}` : ""}
          </p>
        </div>
      )}

      {editing && (
        <Card>
          <CardContent className="space-y-6 py-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Business name</Label>
                <Input
                  value={draft.business_name}
                  onChange={(e) => setDraft((d) => ({ ...d, business_name: e.target.value }))}
                />
                {fieldErrors.business_name && (
                  <p className="text-xs text-destructive">{fieldErrors.business_name.join(" ")}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>GSTIN</Label>
                <Input
                  value={draft.gstin}
                  onChange={(e) => setDraft((d) => ({ ...d, gstin: e.target.value }))}
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
                  value={draft.email}
                  onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
                />
                {fieldErrors.email && (
                  <p className="text-xs text-destructive">{fieldErrors.email.join(" ")}</p>
                )}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Address</Label>
              <Textarea
                value={draft.address}
                onChange={(e) => setDraft((d) => ({ ...d, address: e.target.value }))}
              />
            </div>

            <div className="border-t pt-4">
              <h3 className="mb-3 text-sm font-medium">Tax & numbering</h3>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Currency</Label>
                  <Input
                    value={draft.currency}
                    onChange={(e) => setDraft((d) => ({ ...d, currency: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Default GST rate (%)</Label>
                  <Input
                    value={draft.default_tax_rate ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, default_tax_rate: e.target.value }))}
                  />
                </div>
                <div />
                <div className="flex flex-col gap-1.5">
                  <Label>SKU prefix</Label>
                  <Input
                    placeholder="HEX"
                    value={draft.sku_prefix}
                    onChange={(e) => setDraft((d) => ({ ...d, sku_prefix: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Serial prefix</Label>
                  <Input
                    placeholder="HX"
                    value={draft.serial_prefix}
                    onChange={(e) => setDraft((d) => ({ ...d, serial_prefix: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Serial padding</Label>
                  <Input
                    placeholder="6"
                    value={draft.serial_padding ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, serial_padding: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Invoice prefix</Label>
                  <Input
                    placeholder="HEX-INV"
                    value={draft.invoice_prefix}
                    onChange={(e) => setDraft((d) => ({ ...d, invoice_prefix: e.target.value }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Invoice padding</Label>
                  <Input
                    placeholder="6"
                    value={draft.invoice_padding ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, invoice_padding: e.target.value }))}
                  />
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Leave a prefix/padding field blank to keep using the server default.
              </p>
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
    </div>
  );
}
