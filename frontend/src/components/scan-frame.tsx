import { cn } from "@/lib/utils";

/** Corner brackets + sweeping line -- the barcode scanner's viewfinder look
 * (Phase 6, `features/scanner`), reused as a generic "processing" indicator. */
export function ScanFrameMarks({
  size = "md",
  className,
}: {
  size?: "sm" | "md";
  className?: string;
}) {
  const box = size === "sm" ? "size-8" : "aspect-square w-2/5 min-w-20";
  const corner = size === "sm" ? "absolute size-2.5 border-white/80" : "absolute size-7 border-white/80";
  return (
    <div className={cn("relative", box, className)}>
      <span className={`${corner} left-0 top-0 border-l-2 border-t-2`} />
      <span className={`${corner} right-0 top-0 border-r-2 border-t-2`} />
      <span className={`${corner} bottom-0 left-0 border-b-2 border-l-2`} />
      <span className={`${corner} bottom-0 right-0 border-b-2 border-r-2`} />
      <span className="animate-scanline absolute inset-x-1 top-1/2 h-0.5 -translate-y-1/2 rounded bg-sky-400/80" />
    </div>
  );
}

/** A dark box with `ScanFrameMarks` centered and an optional caption -- the
 * standalone (non-overlay) form used for invoice/report processing states. */
export function ScanFrame({ message, className }: { message?: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex w-full flex-col items-center justify-center gap-3 bg-slate-950 py-10 text-white",
        className,
      )}
    >
      <ScanFrameMarks />
      {message && <p className="px-4 text-center text-xs text-white/70">{message}</p>}
    </div>
  );
}
