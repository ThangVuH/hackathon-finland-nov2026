import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { Crosshair, Maximize, Minus, Plus, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Detection } from "@/lib/detections";
import { ACCEPTED_TYPES } from "@/lib/image-prep";

export interface Drawing {
  id: string;
  name: string;
  src: string;
  /** Original upload, kept when src is only a preview image. */
  fileUrl?: string;
  kind: "sample" | "upload";
}

export interface DrawingCanvasHandle {
  focusDetection: (index: number) => void;
}

interface View {
  x: number;
  y: number;
  z: number;
}

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 12;
const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

interface Props {
  drawing: Drawing;
  detections: Detection[];
  showBoxes: boolean;
  highlighted: number | null;
  analyzing: boolean;
  onHoverDetection: (index: number | null) => void;
  onSelectDetection: (index: number) => void;
  onFiles: (files: FileList | File[]) => void;
  handleRef?: Ref<DrawingCanvasHandle>;
}

export function DrawingCanvas({
  drawing,
  detections,
  showBoxes,
  highlighted,
  analyzing,
  onHoverDetection,
  onSelectDetection,
  onFiles,
  handleRef,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [view, setView] = useState<View>({ x: 0, y: 0, z: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const [animate, setAnimate] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [dropActive, setDropActive] = useState(false);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const pan = useRef<{ id: number; sx: number; sy: number; vx: number; vy: number; moved: boolean } | null>(null);

  const withAnimation = useCallback((next: View) => {
    setAnimate(true);
    setView(next);
    window.setTimeout(() => setAnimate(false), 380);
  }, []);

  const fitView = useCallback(
    (animated = true) => {
      const el = containerRef.current;
      if (!el || !natural) return;
      const pad = 48;
      const z = clampZoom(Math.min((el.clientWidth - pad * 2) / natural.w, (el.clientHeight - pad * 2) / natural.h));
      const next = { z, x: (el.clientWidth - natural.w * z) / 2, y: (el.clientHeight - natural.h * z) / 2 };
      if (animated) withAnimation(next);
      else setView(next);
    },
    [natural, withAnimation],
  );

  const imgRef = useRef<HTMLImageElement>(null);
  // The image may finish loading before hydration attaches onLoad, so read it directly too.
  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete && img.naturalWidth) setNatural({ w: img.naturalWidth, h: img.naturalHeight });
    else setNatural(null);
  }, [drawing.src]);

  useEffect(() => {
    if (natural) fitView(false);
  }, [natural, fitView]);

  const zoomAt = useCallback((factor: number, px: number, py: number, animated = false) => {
    const v = viewRef.current;
    const z = clampZoom(v.z * factor);
    const k = z / v.z;
    const next = { z, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    if (animated) withAnimation(next);
    else setView(next);
  }, [withAnimation]);

  // Native non-passive wheel listener so preventDefault works (zoom + trackpad pinch).
  const wheelRef = useRef<(e: WheelEvent) => void>(() => {});
  wheelRef.current = (e: WheelEvent) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 100 : 1);
    const intensity = e.ctrlKey ? 0.01 : 0.0015;
    zoomAt(Math.exp(-dy * intensity), e.clientX - rect.left, e.clientY - rect.top);
  };
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      wheelRef.current(e);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomButton = (factor: number) => {
    const el = containerRef.current;
    if (!el) return;
    zoomAt(factor, el.clientWidth / 2, el.clientHeight / 2, true);
  };

  useImperativeHandle(
    handleRef,
    () => ({
      focusDetection: (index: number) => {
        const el = containerRef.current;
        const d = detections[index];
        if (!el || !natural || !d) return;
        const [ymin, xmin, ymax, xmax] = d.box;
        const bw = ((xmax - xmin) / 1000) * natural.w;
        const bh = ((ymax - ymin) / 1000) * natural.h;
        const cx = ((xmin + xmax) / 2000) * natural.w;
        const cy = ((ymin + ymax) / 2000) * natural.h;
        const fit = Math.min(el.clientWidth / natural.w, el.clientHeight / natural.h);
        const z = clampZoom(Math.min((el.clientWidth * 0.3) / bw, (el.clientHeight * 0.3) / bh, fit * 3));
        withAnimation({ z, x: el.clientWidth / 2 - cx * z, y: el.clientHeight / 2 - cy * z });
      },
    }),
    [detections, natural, withAnimation],
  );

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const v = viewRef.current;
    pan.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, vx: v.x, vy: v.y, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const el = containerRef.current;
    if (el && natural) {
      const rect = el.getBoundingClientRect();
      const v = viewRef.current;
      const ix = (e.clientX - rect.left - v.x) / v.z;
      const iy = (e.clientY - rect.top - v.y) / v.z;
      if (ix >= 0 && iy >= 0 && ix <= natural.w && iy <= natural.h) {
        setCursor({ x: Math.round((ix / natural.w) * 1000), y: Math.round((iy / natural.h) * 1000) });
      } else setCursor(null);
    }
    const p = pan.current;
    if (!p || p.id !== e.pointerId) return;
    const dx = e.clientX - p.sx;
    const dy = e.clientY - p.sy;
    if (!p.moved && Math.hypot(dx, dy) > 3) {
      p.moved = true;
      setDragging(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    }
    if (p.moved) setView((v) => ({ ...v, x: p.vx + dx, y: p.vy + dy }));
  };
  const endPan = (e: React.PointerEvent) => {
    const p = pan.current;
    if (p?.moved) {
      // Swallow the click that follows a drag.
      const stop = (ev: Event) => {
        ev.stopPropagation();
        window.removeEventListener("click", stop, true);
      };
      window.addEventListener("click", stop, true);
      window.setTimeout(() => window.removeEventListener("click", stop, true), 0);
    }
    if (p && (e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    }
    pan.current = null;
    setDragging(false);
  };

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-canvas">
      {/* Toolbar */}
      <div className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-border bg-panel px-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="label-tech">Sheet</span>
          <span className="truncate font-mono text-xs text-foreground">{drawing.name}</span>
          {natural && (
            <span className="hidden font-mono text-[0.7rem] text-muted-foreground sm:inline">
              {natural.w}×{natural.h}px
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <ToolButton label="Zoom out" onClick={() => zoomButton(1 / 1.4)}>
            <Minus className="size-4" />
          </ToolButton>
          <span className="w-14 text-center font-mono text-xs tabular-nums text-foreground">
            {Math.round(view.z * 100)}%
          </span>
          <ToolButton label="Zoom in" onClick={() => zoomButton(1.4)}>
            <Plus className="size-4" />
          </ToolButton>
          <div className="mx-1 h-5 w-px bg-border" />
          <ToolButton label="Reset view" onClick={() => fitView(true)}>
            <Maximize className="size-4" />
          </ToolButton>
        </div>
      </div>

      {/* Viewport */}
      <div
        ref={containerRef}
        className={cn(
          "bg-blueprint-grid relative min-h-0 flex-1 touch-none overflow-hidden select-none",
          dragging ? "cursor-grabbing" : "cursor-grab",
        )}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPan}
        onPointerCancel={endPan}
        onPointerLeave={() => setCursor(null)}
        onDoubleClick={() => fitView(true)}
        onDragOver={(e) => {
          e.preventDefault();
          setDropActive(true);
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setDropActive(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDropActive(false);
          if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
        }}
      >
        <div
          className={cn("absolute top-0 left-0 origin-top-left", animate && "transition-transform duration-[360ms] ease-out")}
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})`,
            width: natural?.w,
            height: natural?.h,
            ["--z" as string]: view.z,
          }}
        >
          <img
            key={drawing.src}
            ref={imgRef}
            src={drawing.src}
            alt={drawing.name}
            draggable={false}
            onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            className={cn("block max-w-none shadow-panel", !natural && "opacity-0")}
            style={natural ? { width: natural.w, height: natural.h } : undefined}
          />

          {natural && showBoxes && detections.some((d) => (d.polygon?.length ?? 0) > 2) && (
            <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" viewBox="0 0 1000 1000" preserveAspectRatio="none">
              {detections.map((d, i) =>
                d.polygon && d.polygon.length > 2 ? (
                  <polygon
                    key={i}
                    points={d.polygon.map(([x, y]) => `${x},${y}`).join(" ")}
                    className={highlighted === i ? "fill-safety/30 stroke-safety" : "fill-scan/15 stroke-scan"}
                    strokeWidth={1.5}
                  />
                ) : null,
              )}
            </svg>
          )}

          {natural && showBoxes &&
            detections.map((d, i) => {
              const [ymin, xmin, ymax, xmax] = d.box;
              if (ymax - ymin < 1 || xmax - xmin < 1) return null;
              const active = highlighted === i;
              const dropped = d.included === false;
              const disputed = d.disputed === true && !dropped;
              return (
                <button
                  key={i}
                  type="button"
                  aria-label={`${d.tag}${d.disputed ? ", disputed" : ""}${dropped ? ", dropped" : ""}${d.label ? `: ${d.label}` : ""}`}
                  onPointerEnter={() => onHoverDetection(i)}
                  onPointerLeave={() => onHoverDetection(null)}
                  onClick={() => onSelectDetection(i)}
                  className={cn(
                    "absolute cursor-pointer rounded-[1px] transition-colors",
                    dropped && "z-10 border-dashed border-muted-foreground/80 bg-transparent",
                    !dropped && active && "z-20 animate-box-pulse border-solid border-safety",
                    !dropped && !active && disputed && "z-10 border-solid border-safety bg-safety/20",
                    !dropped && !active && !disputed && "z-10 border-solid border-scan bg-scan/10 hover:bg-scan/20",
                  )}
                  style={{
                    top: `${ymin / 10}%`,
                    left: `${xmin / 10}%`,
                    height: `${(ymax - ymin) / 10}%`,
                    width: `${(xmax - xmin) / 10}%`,
                    borderWidth: `calc(${active ? 3 : 2}px / var(--z))`,
                  }}
                >
                  <span
                    className={cn(
                      "pointer-events-none absolute bottom-full left-0 origin-bottom-left font-mono text-[11px] leading-none font-semibold whitespace-nowrap",
                      active ? "bg-safety text-safety-foreground" : "bg-scan text-scan-foreground",
                    )}
                    style={{
                      transform: `translate(calc(-${active ? 3 : 2}px / var(--z)), 0) scale(calc(1 / var(--z)))`,
                      padding: "3px 5px",
                    }}
                  >
                    {dropped ? `${d.tag} off` : disputed ? `${d.tag} ?` : d.tag}
                  </span>
                </button>
              );
            })}

          {analyzing && natural && (
            <div className="pointer-events-none absolute inset-0 overflow-hidden">
              <div className="absolute inset-x-0 top-0 h-[10%] animate-scan-sweep bg-gradient-to-b from-transparent via-scan/25 to-scan/60 border-b-2 border-scan" />
            </div>
          )}
        </div>

        {dropActive && (
          <div className="pointer-events-none absolute inset-4 z-30 flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed border-safety bg-background/80">
            <Upload className="size-8 text-safety" />
            <p className="font-display text-xl text-foreground">Drop drawing to load</p>
            <p className="label-tech">PNG · JPG · WEBP</p>
          </div>
        )}

        {/* Status readout */}
        <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-3 rounded-sm border border-border bg-panel/90 px-2.5 py-1.5 font-mono text-[0.7rem] text-muted-foreground backdrop-blur">
          <Crosshair className="size-3.5 text-scan" />
          <span className="tabular-nums">
            Y <span className="text-foreground">{cursor ? String(cursor.y).padStart(4, "0") : "----"}</span>
          </span>
          <span className="tabular-nums">
            X <span className="text-foreground">{cursor ? String(cursor.x).padStart(4, "0") : "----"}</span>
          </span>
          <span className="hidden md:inline">· scroll to zoom · drag to pan · dbl-click to fit</span>
        </div>
        {showBoxes && detections.length > 0 && (
          <div className="pointer-events-none absolute right-3 bottom-3 rounded-sm border border-scan/50 bg-panel/90 px-2.5 py-1.5 font-mono text-[0.7rem] text-scan backdrop-blur">
            {detections.filter((d) => d.included !== false).length} IN COUNT
            {detections.some((d) => d.disputed) ? " · CLICK A ? BOX" : ""}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex size-8 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {children}
    </button>
  );
}

export function isAcceptedFile(file: File) {
  return ACCEPTED_TYPES.includes(file.type) || /\.(pdf|ifc)$/i.test(file.name);
}
