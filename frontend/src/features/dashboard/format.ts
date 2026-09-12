export function money(value: string | number): string {
  const n = Number(value);
  return Number.isNaN(n)
    ? String(value)
    : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}
