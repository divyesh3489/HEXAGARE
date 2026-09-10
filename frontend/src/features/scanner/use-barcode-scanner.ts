import { useCallback, useEffect, useRef, useState } from "react";
import {
  BrowserCodeReader,
  BrowserMultiFormatReader,
  type IScannerControls,
} from "@zxing/browser";
import { BarcodeFormat, DecodeHintType, NotFoundException } from "@zxing/library";

/** Where the camera pipeline is right now. */
export type ScannerState =
  | "idle" // not started (or stopped)
  | "starting" // getUserMedia in flight
  | "scanning" // live, decoding frames
  | "denied" // permission blocked
  | "no-camera" // no video input on this device
  | "error"; // camera in use / unknown failure

/** Formats we ask ZXing to look for. Phase 5 labels are Code 128; the retail
 * 1D symbologies and QR are included so a stray EAN/UPC/QR still resolves. */
const POSSIBLE_FORMATS = [
  BarcodeFormat.CODE_128,
  BarcodeFormat.CODE_39,
  BarcodeFormat.CODE_93,
  BarcodeFormat.ITF,
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.UPC_A,
  BarcodeFormat.UPC_E,
  BarcodeFormat.QR_CODE,
];

function buildHints(): Map<DecodeHintType, unknown> {
  const hints = new Map<DecodeHintType, unknown>();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, POSSIBLE_FORMATS);
  hints.set(DecodeHintType.TRY_HARDER, true);
  return hints;
}

function classifyError(err: unknown): { state: ScannerState; message: string } {
  const name = (err as { name?: string } | null)?.name ?? "";
  if (["NotAllowedError", "PermissionDeniedError", "SecurityError"].includes(name)) {
    return {
      state: "denied",
      message:
        "Camera access was blocked. Allow it in your browser's site settings, or type the serial below.",
    };
  }
  if (["NotFoundError", "DevicesNotFoundError", "OverconstrainedError"].includes(name)) {
    return {
      state: "no-camera",
      message: "No camera was found on this device — type the serial below instead.",
    };
  }
  if (["NotReadableError", "TrackStartError", "AbortError"].includes(name)) {
    return {
      state: "error",
      message: "The camera is busy in another app. Close it and try again.",
    };
  }
  if (name === "ScannerTimeoutError") {
    return {
      state: "error",
      message:
        "The camera didn't start. Try again, or type the serial below.",
    };
  }
  return {
    state: "error",
    message: err instanceof Error ? err.message : "Could not start the camera.",
  };
}

/** If getUserMedia neither resolves nor rejects within this window (some
 * mobile browsers just hang when the camera can't be acquired), bail out to
 * an error state instead of a permanent "starting…" spinner. */
const START_TIMEOUT_MS = 15_000;

class ScannerTimeoutError extends Error {
  override name = "ScannerTimeoutError";
}

interface Options {
  /** Called once per successful decode with the raw barcode text. */
  onDecode: (text: string) => void;
}

export interface BarcodeScanner {
  state: ScannerState;
  errorMessage: string | null;
  /** Attach to the page's <video> element. */
  videoRef: React.RefObject<HTMLVideoElement>;
  /** Named video inputs (populated once permission is granted). */
  devices: MediaDeviceInfo[];
  activeDeviceId: string | undefined;
  /** True when this browser can do camera capture at all (secure context). */
  isSupported: boolean;
  start: () => void;
  stop: () => void;
  switchCamera: () => void;
}

/** Wraps ZXing's continuous video decoder: start/stop, device switching,
 * permission/error state. `start` is meant to be called from a user gesture so
 * the permission prompt is tied to a tap. */
export function useBarcodeScanner({ onDecode }: Options): BarcodeScanner {
  const videoRef = useRef<HTMLVideoElement>(null);
  const readerRef = useRef<BrowserMultiFormatReader | null>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const decodedRef = useRef(false);
  /** Bumped on every start/stop; a resolution from an older run is discarded. */
  const runIdRef = useRef(0);
  const onDecodeRef = useRef(onDecode);
  onDecodeRef.current = onDecode;

  const [state, setState] = useState<ScannerState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [activeDeviceId, setActiveDeviceId] = useState<string | undefined>(undefined);

  const isSupported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function";

  const teardown = useCallback(() => {
    runIdRef.current += 1;
    controlsRef.current?.stop();
    controlsRef.current = null;
    const stream = videoRef.current?.srcObject;
    if (stream instanceof MediaStream) {
      for (const track of stream.getTracks()) track.stop();
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const stop = useCallback(() => {
    teardown();
    setState("idle");
  }, [teardown]);

  const startWith = useCallback(
    async (deviceId: string | undefined) => {
      if (!isSupported || !videoRef.current) return;
      teardown();
      const runId = runIdRef.current;
      decodedRef.current = false;
      setErrorMessage(null);
      setState("starting");

      if (!readerRef.current) {
        readerRef.current = new BrowserMultiFormatReader(buildHints());
      }

      try {
        const decodeStarted = readerRef.current.decodeFromVideoDevice(
          deviceId,
          videoRef.current,
          (result, err) => {
            if (runIdRef.current !== runId) return;
            if (result && !decodedRef.current) {
              decodedRef.current = true;
              onDecodeRef.current(result.getText());
              return;
            }
            // NotFoundException fires on every frame without a code — expected.
            if (err && !(err instanceof NotFoundException)) {
              console.debug("scanner: decode error", err);
            }
          },
        );
        // If the camera does eventually come up after we've moved on (timeout
        // fired, or the user restarted), make sure that late stream is stopped.
        void decodeStarted
          .then((late) => {
            if (runIdRef.current !== runId) late.stop();
          })
          .catch(() => {});

        const timeout = new Promise<never>((_, reject) => {
          setTimeout(
            () => reject(new ScannerTimeoutError("camera-start-timeout")),
            START_TIMEOUT_MS,
          );
        });
        const controls = await Promise.race([decodeStarted, timeout]);

        // A stop()/restart happened while we were waiting — drop this stream.
        if (runIdRef.current !== runId) {
          controls.stop();
          return;
        }
        controlsRef.current = controls;
        setActiveDeviceId(deviceId);
        setState("scanning");

        // Labels are only readable after permission is granted.
        try {
          const list = await BrowserCodeReader.listVideoInputDevices();
          setDevices(list);
          if (!deviceId && list.length > 0) {
            const back = list.find((d) => /back|rear|environment/i.test(d.label));
            setActiveDeviceId(back?.deviceId ?? list[0]?.deviceId);
          }
        } catch {
          /* enumeration is best-effort — the switch button just won't show */
        }
      } catch (err) {
        if (runIdRef.current !== runId) return;
        teardown();
        const { state: nextState, message } = classifyError(err);
        setState(nextState);
        setErrorMessage(message);
      }
    },
    [isSupported, teardown],
  );

  const start = useCallback(() => {
    void startWith(activeDeviceId);
  }, [startWith, activeDeviceId]);

  const switchCamera = useCallback(() => {
    if (devices.length < 2) return;
    const currentIndex = activeDeviceId
      ? devices.findIndex((d) => d.deviceId === activeDeviceId)
      : 0;
    const next = devices[(currentIndex + 1) % devices.length];
    if (next) void startWith(next.deviceId);
  }, [devices, activeDeviceId, startWith]);

  // Release the camera when the page unmounts.
  useEffect(() => teardown, [teardown]);

  return {
    state,
    errorMessage,
    videoRef,
    devices,
    activeDeviceId,
    isSupported,
    start,
    stop,
    switchCamera,
  };
}
