import { detectionKind } from "./detections";

export interface MarkPaint {
  box: string;
  badge: string;
  swatch: string;
  dashed: boolean;
}

const PAINT: Record<string, MarkPaint> = {
  door: {
    box: "border-scan bg-scan/15",
    badge: "bg-scan text-scan-foreground",
    swatch: "bg-scan",
    dashed: false,
  },
  window: {
    box: "border-amber-300 bg-amber-300/15",
    badge: "bg-amber-300 text-neutral-950",
    swatch: "bg-amber-300",
    dashed: true,
  },
  room: {
    box: "border-safety bg-safety/10",
    badge: "bg-safety text-safety-foreground",
    swatch: "bg-safety",
    dashed: false,
  },
  column: {
    box: "border-lime-300 bg-lime-300/25",
    badge: "bg-lime-300 text-neutral-950",
    swatch: "bg-lime-300",
    dashed: false,
  },
  stair: {
    box: "border-fuchsia-400 bg-fuchsia-400/15",
    badge: "bg-fuchsia-400 text-neutral-950",
    swatch: "bg-fuchsia-400",
    dashed: true,
  },
};

const FALLBACK: MarkPaint = {
  box: "border-scan bg-scan/10",
  badge: "bg-scan text-scan-foreground",
  swatch: "bg-scan",
  dashed: false,
};

export function markPaint(tag: string): MarkPaint {
  return PAINT[detectionKind(tag)] ?? FALLBACK;
}
