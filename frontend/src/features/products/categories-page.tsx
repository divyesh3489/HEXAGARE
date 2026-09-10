import { useState } from "react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useHasPermission } from "@/hooks/use-auth";
import { useCategories, useCategoryMutations } from "./hooks";
import type { Category } from "./types";

interface Draft {
  name: string;
  code: string;
  parent: string;
  description: string;
  is_active: boolean;
}

const EMPTY: Draft = { name: "", code: "", parent: "", description: "", is_active: true };

export function CategoriesPage() {
  const canManage = useHasPermission()("products.manage");
  const [search, setSearch] = useState("");
  const { data, isPending, error } = useCategories({ search, page_size: 200 });
  const { create, update, remove } = useCategoryMutations();

  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const categories = data?.data ?? [];

  const startNew = () => {
    setDraft(EMPTY);
    setEditingId("new");
    setFormError(null);
    setFieldErrors({});
  };
  const startEdit = (c: Category) => {
    setDraft({
      name: c.name,
      code: c.code,
      parent: c.parent ? String(c.parent) : "",
      description: c.description,
      is_active: c.is_active,
    });
    setEditingId(c.id);
    setFormError(null);
    setFieldErrors({});
  };
  const cancel = () => {
    setEditingId(null);
    setDraft(EMPTY);
  };

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    const body = {
      name: draft.name,
      code: draft.code,
      parent: draft.parent ? Number(draft.parent) : null,
      description: draft.description,
      is_active: draft.is_active,
    };
    try {
      if (editingId === "new") await create.mutateAsync(body);
      else if (typeof editingId === "number") await update.mutateAsync({ id: editingId, body });
      cancel();
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save the category.");
      }
    }
  };

  return (
    <div>
      <PageHeader
        title="Categories"
        description="Organise the catalog. Category codes feed SKU suggestions."
        actions={
          canManage && editingId === null ? (
            <Button onClick={startNew}>New category</Button>
          ) : undefined
        }
      />

      <div className="mb-4">
        <Input
          placeholder="Search categories…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {editingId !== null && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">
              {editingId === "new" ? "New category" : "Edit category"}
            </h3>
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
                <Label>Code (for SKUs)</Label>
                <Input
                  value={draft.code}
                  onChange={(e) => setDraft((d) => ({ ...d, code: e.target.value }))}
                  placeholder="e.g. MP"
                  className="font-mono"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Parent category</Label>
                <select
                  value={draft.parent}
                  onChange={(e) => setDraft((d) => ({ ...d, parent: e.target.value }))}
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                >
                  <option value="">— None (top level) —</option>
                  {categories
                    .filter((c) => c.id !== editingId)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </div>
              <label className="flex items-center gap-2 self-end text-sm">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
                />
                Active
              </label>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Description</Label>
              <Textarea
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={create.isPending || update.isPending}>
                Save
              </Button>
              <Button variant="outline" onClick={cancel}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">Couldn’t load categories.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Code</th>
                  <th className="px-4 py-3 font-medium">Parent</th>
                  <th className="px-4 py-3 font-medium">Products</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  {canManage && <th className="px-4 py-3" />}
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
                {!isPending && categories.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No categories yet.
                    </td>
                  </tr>
                )}
                {categories.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-medium">{c.name}</td>
                    <td className="px-4 py-3 font-mono text-muted-foreground">{c.code || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.parent_name ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.product_count}</td>
                    <td className="px-4 py-3">
                      {c.is_active ? (
                        <Badge>Active</Badge>
                      ) : (
                        <Badge variant="muted">Inactive</Badge>
                      )}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => startEdit(c)}>
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              if (confirm(`Delete category “${c.name}”?`)) remove.mutate(c.id);
                            }}
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    )}
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
