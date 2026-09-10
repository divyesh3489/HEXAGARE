import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { skuApi } from "./api";

interface SkuFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Context for the auto-suggestion call. */
  suggestContext: {
    category?: number | null;
    product?: number | null;
    variant_code?: string;
    attribute_values?: string[];
  };
  /** Variant being edited, so it doesn't clash with its own SKU. */
  excludeVariantId?: number;
  disabled?: boolean;
}

type Availability = "idle" | "checking" | "available" | "taken";

/** SKU input with an auto-suggest button and a live availability check.
 *  The suggestion is advisory — the field stays fully editable. */
export function SkuField({
  value,
  onChange,
  suggestContext,
  excludeVariantId,
  disabled,
}: SkuFieldProps) {
  const [suggesting, setSuggesting] = useState(false);
  const [availability, setAvailability] = useState<Availability>("idle");
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    const sku = value.trim();
    if (!sku) {
      setAvailability("idle");
      return;
    }
    setAvailability("checking");
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await skuApi.check(sku, excludeVariantId);
        setAvailability(res.available ? "available" : "taken");
      } catch {
        setAvailability("idle");
      }
    }, 400);
    return () => clearTimeout(debounceRef.current);
  }, [value, excludeVariantId]);

  const suggest = async () => {
    setSuggesting(true);
    setError(null);
    try {
      const res = await skuApi.suggest(suggestContext);
      onChange(res.sku);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t suggest a SKU.");
    } finally {
      setSuggesting(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Auto-suggested — editable"
          className="font-mono"
          disabled={disabled}
        />
        <Button
          type="button"
          variant="outline"
          onClick={suggest}
          disabled={disabled || suggesting}
        >
          {suggesting ? "…" : "Suggest"}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {!error && availability === "taken" && (
        <p className="text-xs text-destructive">This SKU is already in use.</p>
      )}
      {!error && availability === "available" && value.trim() && (
        <p className="text-xs text-muted-foreground">SKU is available.</p>
      )}
    </div>
  );
}
