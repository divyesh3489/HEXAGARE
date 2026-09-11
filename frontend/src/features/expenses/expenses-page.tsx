import { useState } from "react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSalesChannels } from "@/features/sales/hooks";
import { useHasPermission } from "@/hooks/use-auth";
import { useExpenseMutations, useExpenses } from "./hooks";
import { EXPENSE_CATEGORIES, EXPENSE_CATEGORY_LABELS, type ExpenseWriteBody } from "./types";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm " +
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

/** `YYYY-MM-DD` in the viewer's local calendar -- `toISOString()` converts
 * through UTC first, which silently shifts the date near midnight in any
 * timezone ahead of UTC. */
function today(): string {
  const d = new Date();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

function emptyDraft(): ExpenseWriteBody {
  return { category: "OTHER", sales_channel: null, amount: "", expense_date: today(), note: "" };
}

function money(value: string): string {
  const n = Number(value);
  return Number.isNaN(n) ? value : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

export function ExpensesPage() {
  const canManage = useHasPermission()("expenses.manage");
  const { data: channels } = useSalesChannels();

  const [category, setCategory] = useState("");
  const [channel, setChannel] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const { data, isPending, error } = useExpenses({
    category: category || undefined,
    channel: channel || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page_size: 200,
  });
  const { create, remove } = useExpenseMutations();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ExpenseWriteBody>(emptyDraft());
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const expenses = data?.data ?? [];

  const startNew = () => {
    setDraft(emptyDraft());
    setCreating(true);
    setFormError(null);
    setFieldErrors({});
  };
  const cancel = () => {
    setCreating(false);
    setDraft(emptyDraft());
  };

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    try {
      await create.mutateAsync({
        ...draft,
        sales_channel: draft.sales_channel || undefined,
        note: draft.note || undefined,
      });
      cancel();
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save the expense.");
      }
    }
  };

  return (
    <div>
      <PageHeader
        title="Expenses"
        description="Packaging, shipping, advertising and other costs -- rolled up into the Profit summary."
        actions={
          canManage && !creating ? <Button onClick={startNew}>New expense</Button> : undefined
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          className={selectClass}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">All categories</option>
          {EXPENSE_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {EXPENSE_CATEGORY_LABELS[c]}
            </option>
          ))}
        </select>
        <select className={selectClass} value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {(channels?.data ?? []).map((ch) => (
            <option key={ch.id} value={ch.code}>
              {ch.name}
            </option>
          ))}
        </select>
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="w-auto"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="w-auto"
        />
      </div>

      {creating && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">New expense</h3>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Category</Label>
                <select
                  className={selectClass}
                  value={draft.category}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, category: e.target.value as ExpenseWriteBody["category"] }))
                  }
                >
                  {EXPENSE_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {EXPENSE_CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Channel (optional)</Label>
                <select
                  className={selectClass}
                  value={draft.sales_channel ?? ""}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      sales_channel: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                >
                  <option value="">General / business-wide</option>
                  {(channels?.data ?? []).map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      {ch.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Amount (₹)</Label>
                <Input
                  value={draft.amount}
                  onChange={(e) => setDraft((d) => ({ ...d, amount: e.target.value }))}
                />
                {fieldErrors.amount && (
                  <p className="text-xs text-destructive">{fieldErrors.amount.join(" ")}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Date</Label>
                <Input
                  type="date"
                  value={draft.expense_date}
                  onChange={(e) => setDraft((d) => ({ ...d, expense_date: e.target.value }))}
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Note</Label>
              <Input
                value={draft.note}
                onChange={(e) => setDraft((d) => ({ ...d, note: e.target.value }))}
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

      {error && <p className="text-sm text-destructive">Couldn’t load expenses.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Category</th>
                  <th className="px-4 py-3 font-medium">Channel</th>
                  <th className="px-4 py-3 font-medium">Note</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
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
                {!isPending && expenses.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No expenses yet.
                    </td>
                  </tr>
                )}
                {expenses.map((expense) => (
                  <tr key={expense.id} className="border-b last:border-0">
                    <td className="px-4 py-3 whitespace-nowrap">{expense.expense_date}</td>
                    <td className="px-4 py-3">{expense.category_display}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {expense.sales_channel_code ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{expense.note || "—"}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(expense.amount)}</td>
                    {canManage && (
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => remove.mutate(expense.id)}
                          disabled={remove.isPending}
                        >
                          Delete
                        </Button>
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
