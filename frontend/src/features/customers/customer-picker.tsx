import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { customersApi } from "./api";
import type { CustomerListItem } from "./types";

/** Debounces a raw text input by `delay` ms (same inline pattern used
 * elsewhere in this app -- no shared hook exists yet). */
function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

interface SelectedCustomer {
  id: number;
  name: string;
}

/** Search-or-walk-in-quick-add customer picker for the POS flow
 * (HEXAGARE_FEATURES.md section 30) -- search an existing customer, or add a
 * walk-in with just a name/phone and attach it in one step. */
export function CustomerPicker({
  selected,
  onSelect,
  disabled,
}: {
  selected: SelectedCustomer | null;
  onSelect: (customer: SelectedCustomer | null) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [addingWalkIn, setAddingWalkIn] = useState(false);
  const [walkInName, setWalkInName] = useState("");
  const [walkInPhone, setWalkInPhone] = useState("");
  const [walkInError, setWalkInError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const debounced = useDebounced(text);
  const { data, isFetching } = useQuery({
    queryKey: ["customers", "picker-search", debounced],
    queryFn: () => customersApi.list({ search: debounced, page_size: 10 }),
    enabled: debounced.trim().length >= 2,
  });
  const results = data?.data ?? [];

  const pick = (customer: CustomerListItem | SelectedCustomer) => {
    onSelect({ id: customer.id, name: customer.name });
    setText("");
  };

  const addWalkIn = async () => {
    setWalkInError(null);
    if (!walkInName.trim()) {
      setWalkInError("Name is required.");
      return;
    }
    setCreating(true);
    try {
      const created = await customersApi.create({
        name: walkInName.trim(),
        phone: walkInPhone.trim(),
        type: "WALK_IN",
      });
      pick(created);
      setAddingWalkIn(false);
      setWalkInName("");
      setWalkInPhone("");
    } catch (err) {
      setWalkInError(err instanceof ApiError ? err.detail : "Couldn't add this customer.");
    } finally {
      setCreating(false);
    }
  };

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-2 text-sm">
        <span>
          Customer: <span className="font-medium">{selected.name}</span>
        </span>
        {!disabled && (
          <Button size="sm" variant="ghost" onClick={() => onSelect(null)}>
            Change
          </Button>
        )}
      </div>
    );
  }

  if (disabled) {
    return <p className="text-sm text-muted-foreground">No customer on this bill.</p>;
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search customer by name or phone…"
          autoComplete="off"
        />
        {debounced.trim().length >= 2 && (
          <Card className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto py-1">
            {isFetching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
            {!isFetching && results.length === 0 && (
              <p className="px-3 py-2 text-xs text-muted-foreground">No customers match.</p>
            )}
            {results.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => pick(c)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span>{c.name}</span>
                <span className="text-xs text-muted-foreground">{c.phone}</span>
              </button>
            ))}
          </Card>
        )}
      </div>

      {!addingWalkIn && (
        <Button size="sm" variant="outline" onClick={() => setAddingWalkIn(true)}>
          + Add walk-in customer
        </Button>
      )}

      {addingWalkIn && (
        <div className="flex flex-wrap items-start gap-2">
          <Input
            value={walkInName}
            onChange={(e) => setWalkInName(e.target.value)}
            placeholder="Name"
            className="max-w-[180px]"
          />
          <Input
            value={walkInPhone}
            onChange={(e) => setWalkInPhone(e.target.value)}
            placeholder="Phone (optional)"
            className="max-w-[160px]"
          />
          <Button size="sm" disabled={creating} onClick={addWalkIn}>
            {creating ? "Adding…" : "Add & attach"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setAddingWalkIn(false)}>
            Cancel
          </Button>
          {walkInError && <p className="w-full text-xs text-destructive">{walkInError}</p>}
        </div>
      )}
    </div>
  );
}
