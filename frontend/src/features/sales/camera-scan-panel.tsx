import { useEffect, useRef, useState } from "react";
import { Camera, ScanLine, SwitchCamera, X } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useBarcodeScanner } from "@/features/scanner/use-barcode-scanner";

interface CameraScanPanelProps {
  /** Called once per decoded code (trimmed). The panel then shows a "Scan
   * next" prompt rather than auto-restarting -- mirrors the standalone
   * scanner page's one-decode-at-a-time flow. */
  onAdd: (code: string) => void;
  onClose: () => void;
}

/** Lazy-loaded from `new-bill-page.tsx` behind a "Scan with camera" toggle --
 * ZXing (~465 KB) stays out of New Bill's main chunk, same reasoning as the
 * standalone `/barcode/scan` route (ADR-011). */
export function CameraScanPanel({ onAdd, onClose }: CameraScanPanelProps) {
  const [justScanned, setJustScanned] = useState<string | null>(null);
  const stopRef = useRef<() => void>(() => {});

  const scanner = useBarcodeScanner({
    onDecode: (text) => {
      const code = text.trim();
      setJustScanned(code);
      stopRef.current();
      onAdd(code);
    },
  });
  stopRef.current = scanner.stop;

  const startedRef = useRef(false);
  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      scanner.start();
    }
    return () => scanner.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleScanNext = () => {
    setJustScanned(null);
    scanner.start();
  };

  const { state, errorMessage, isSupported, devices, videoRef } = scanner;
  const showVideo = (state === "starting" || state === "scanning") && !justScanned;

  return (
    <Card className="overflow-hidden">
      <div className="relative aspect-video w-full bg-slate-950 text-white">
        <video
          ref={videoRef}
          className={`size-full object-cover ${showVideo ? "" : "invisible"}`}
          muted
          playsInline
          autoPlay
        />
        {!showVideo && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/70">
            {justScanned ? (
              <>
                <ScanLine className="size-8" />
                <span className="font-mono text-xs">{justScanned}</span>
                <Button size="sm" variant="secondary" onClick={handleScanNext}>
                  Scan next
                </Button>
              </>
            ) : (
              <>
                <Camera className="size-8" />
                <span className="text-xs">
                  {isSupported
                    ? state === "starting"
                      ? "Starting…"
                      : "Camera is off"
                    : "Camera unavailable"}
                </span>
              </>
            )}
          </div>
        )}
        <Button
          size="icon"
          variant="ghost"
          className="absolute right-2 top-2 text-white hover:bg-white/10"
          onClick={onClose}
          aria-label="Close scanner"
        >
          <X />
        </Button>
        {devices.length > 1 && state === "scanning" && (
          <Button
            size="icon"
            variant="ghost"
            className="absolute bottom-2 right-2 text-white hover:bg-white/10"
            onClick={scanner.switchCamera}
            aria-label="Switch camera"
          >
            <SwitchCamera />
          </Button>
        )}
      </div>
      <CardContent className="space-y-2 p-3">
        {!isSupported && (
          <Alert>
            <AlertTitle>Camera not available</AlertTitle>
            <AlertDescription>
              This browser can&apos;t open the camera here — type the serial instead.
            </AlertDescription>
          </Alert>
        )}
        {(state === "denied" || state === "no-camera" || state === "error") && (
          <Alert variant={state === "error" ? "destructive" : "default"}>
            <AlertTitle>
              {state === "denied"
                ? "Camera blocked"
                : state === "no-camera"
                  ? "No camera found"
                  : "Camera error"}
            </AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{errorMessage}</span>
              {state !== "no-camera" && (
                <Button size="sm" variant="outline" onClick={scanner.start}>
                  Try again
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
