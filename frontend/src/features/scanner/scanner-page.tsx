import { useEffect, useRef, useState, type FormEvent } from "react";
import { Camera, Loader2, ScanLine, SwitchCamera } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ScanFrameMarks } from "@/components/scan-frame";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useUnitLookup } from "./hooks";
import { ScanResultCard } from "./scan-result-card";
import { useBarcodeScanner } from "./use-barcode-scanner";

/** Corner brackets + sweeping line drawn over the camera preview. */
function Viewfinder() {
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <ScanFrameMarks className="w-3/5" />
    </div>
  );
}

export function ScannerPage() {
  const [code, setCode] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const usedCameraRef = useRef(false);
  const restartRef = useRef(false);

  const scanner = useBarcodeScanner({
    onDecode: (text) => setCode(text.trim()),
  });
  const { start: startScanner, stop: stopScanner } = scanner;

  const lookup = useUnitLookup(code);

  // Free the camera as soon as we have a code to resolve.
  useEffect(() => {
    if (code !== null) stopScanner();
  }, [code, stopScanner]);

  // "Scan another" clears the code; restart the camera here (after the <video>
  // is back in the tree) rather than from the click handler.
  useEffect(() => {
    if (code === null && restartRef.current) {
      restartRef.current = false;
      startScanner();
    }
  }, [code, startScanner]);

  const handleStart = () => {
    usedCameraRef.current = true;
    scanner.start();
  };

  const handleManualSubmit = (e: FormEvent) => {
    e.preventDefault();
    const value = manual.trim();
    if (!value) return;
    usedCameraRef.current = false;
    setCode(value);
  };

  const handleScanAnother = () => {
    restartRef.current = usedCameraRef.current;
    setManual("");
    setCode(null);
  };

  const { state, errorMessage, isSupported, devices } = scanner;
  const showVideo = state === "starting" || state === "scanning";

  return (
    <div className="mx-auto max-w-md">
      <PageHeader
        title="Scan"
        description="Point the camera at a unit barcode, or type its serial number."
      />

      {code !== null ? (
        <ScanResultCard
          code={code}
          isPending={lookup.isPending}
          error={lookup.error}
          unit={lookup.data}
          onScanAnother={handleScanAnother}
          onRetry={() => lookup.refetch()}
        />
      ) : (
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="relative aspect-square w-full bg-slate-950 text-white">
              {/* Live camera preview — no captions apply. */}
              <video
                ref={scanner.videoRef}
                className={`size-full object-cover ${showVideo ? "" : "invisible"}`}
                muted
                playsInline
                autoPlay
              />
              {showVideo && <Viewfinder />}
              {!showVideo && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/60">
                  <Camera className="size-10" />
                  <span className="text-xs">
                    {isSupported ? "Camera is off" : "Camera unavailable"}
                  </span>
                </div>
              )}
            </div>

            <CardContent className="space-y-3 p-4">
              {!isSupported && (
                <Alert>
                  <AlertTitle>Camera not available</AlertTitle>
                  <AlertDescription>
                    This browser can't open the camera here — it needs a secure
                    (HTTPS or localhost) context. Type the serial below instead.
                  </AlertDescription>
                </Alert>
              )}

              {isSupported && state === "idle" && (
                <Button size="lg" className="w-full" onClick={handleStart}>
                  <ScanLine /> Start scanning
                </Button>
              )}

              {state === "starting" && (
                <Button size="lg" className="w-full" disabled>
                  <Loader2 className="animate-spin" /> Starting camera…
                </Button>
              )}

              {state === "scanning" && (
                <div className="flex items-center gap-2">
                  <Button variant="outline" className="flex-1" onClick={scanner.stop}>
                    Stop
                  </Button>
                  {devices.length > 1 && (
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label="Switch camera"
                      onClick={scanner.switchCamera}
                    >
                      <SwitchCamera />
                    </Button>
                  )}
                </div>
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
                      <Button size="sm" variant="outline" onClick={handleStart}>
                        Try again
                      </Button>
                    )}
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <form onSubmit={handleManualSubmit} className="flex gap-2">
            <Input
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              placeholder="Serial number, e.g. HXMP1123-000001"
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              aria-label="Serial number"
            />
            <Button type="submit" variant="secondary" disabled={!manual.trim()}>
              Look up
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
