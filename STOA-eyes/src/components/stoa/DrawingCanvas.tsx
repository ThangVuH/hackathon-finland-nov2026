import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { Crosshair, Maximize, Minus, Plus, Upload, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { detectionKind, kindSummary, moveBox, resizeBox, type Box, type BoxCorner, type Detection } from "@/lib/detections";
import { markPaint } from "@/lib/mark-style";
import { ACCEPTED_TYPES } from "@/lib/image-prep";

export interface Drawing {
  id: string;
  name: string;
  src: string;
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

const BOX_HANDLES: { corner: BoxCorner; place: string; cursor: string; shift: string }[] = [
  { corner: "nw", place: "top-0 left-0", cursor: "cursor-nwse-resize", shift: "-50%, -50%" },
  { corner: "ne", place: "top-0 right-0", cursor: "cursor-nesw-resize", shift: "50%, -50%" },
  { corner: "sw", place: "bottom-0 left-0", cursor: "cursor-nesw-resize", shift: "-50%, 50%" },
  { corner: "se", place: "bottom-0 right-0", cursor: "cursor-nwse-resize", shift: "50%, 50%" },
];

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 12;
const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

interface Props {
  drawing: Drawing;
  detections: Detection[];
  showBoxes: boolean;
  highlighted: number | null;
  analyzing: boolean;
  badge?: string;
  badgeTitle?: string;
  sourceToggle?: { showingOriginal: boolean; onToggle: () => void } | null;
  onHoverDetection: (index: number | null) => void;
  onSelectDetection: (index: number) => void;
  onMoveDetection?: (index: number, box: Box) => void;
  onDeleteDetection?: (index: number) => void;
  onAddDetection?: (kind: string, box: Box) => void;
  onFiles: (files: FileList | File[]) => void;
  onClose?: () => void;
  handleRef?: Ref<DrawingCanvasHandle>;
}

export function DrawingCanvas({
  drawing,
  detections,
  showBoxes,
  highlighted,
  analyzing,
  badge,
  badgeTitle,
  sourceToggle,
  onHoverDetection,
  onSelectDetection,
  onMoveDetection,
  onDeleteDetection,
  onAddDetection,
  onFiles,
  onClose,
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
  const [addOpen, setAddOpen] = useState(false);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const pan = useRef<{ id: number; sx: number; sy: number; vx: number; vy: number; moved: boolean } | null>(null);
  const boxDrag = useRef<{ id: number; index: number; sx: number; sy: number; box: Box; moved: boolean; corner: BoxCorner | null } | null>(null);
  const moveDetectionRef = useRef(onMoveDetection);
  const selectDetectionRef = useRef(onSelectDetection);
  moveDetectionRef.current = onMoveDetection;
  selectDetectionRef.current = onSelectDetection;

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

  const addDetection = (kind: string) => {
    if (!onAddDetection || !natural) return;
    const el = containerRef.current;
    const viewNow = viewRef.current;
    const centerX = el ? (el.clientWidth / 2 - viewNow.x) / viewNow.z : natural.w / 2;
    const centerY = el ? (el.clientHeight / 2 - viewNow.y) / viewNow.z : natural.h / 2;
    const width = 80;
    const height = 80;
    const left = Math.min(1000 - width, Math.max(0, Math.round((centerX / natural.w) * 1000 - width / 2)));
    const top = Math.min(1000 - height, Math.max(0, Math.round((centerY / natural.h) * 1000 - height / 2)));
    onAddDetection(kind, [top, left, top + height, left + width]);
  };

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

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const drag = boxDrag.current;
      if (!drag || drag.id !== event.pointerId || !natural) return;
      const dx = event.clientX - drag.sx;
      const dy = event.clientY - drag.sy;
      if (!drag.moved && Math.hypot(dx, dy) <= 3) return;
      drag.moved = true;
      setDragging(true);
      const scale = viewRef.current.z;
      const du = (dx / scale / natural.w) * 1000;
      const dv = (dy / scale / natural.h) * 1000;
      moveDetectionRef.current?.(drag.index, drag.corner ? resizeBox(drag.box, drag.corner, du, dv) : moveBox(drag.box, du, dv));
    };
    const end = (event: PointerEvent) => {
      const drag = boxDrag.current;
      if (!drag || drag.id !== event.pointerId) return;
      boxDrag.current = null;
      setDragging(false);
      if (!drag.moved) selectDetectionRef.current(drag.index);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
    };
  }, [natural]);

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
      <div className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-border bg-canvas px-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs text-foreground">{drawing.name}</span>
          {badge && (
            <span className="label-tech shrink-0 text-scan" title={badgeTitle}>
              {badge}
            </span>
          )}
          {natural && (
            <span className="hidden font-mono text-[0.7rem] text-muted-foreground sm:inline">
              {natural.w}×{natural.h}px
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {onAddDetection && showBoxes && (
            <div className="relative mr-1">
              <button
                type="button"
                disabled={analyzing}
                onClick={() => {
                  const kinds = [...new Set(detections.map((item) => detectionKind(item.tag)))].filter((kind) => kind !== "object");
                  if (kinds.length <= 1) {
                    addDetection(kinds[0] ?? "door");
                    setAddOpen(false);
                    return;
                  }
                  setAddOpen((open) => !open);
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border px-2 font-mono text-[0.68rem] text-foreground hover:border-safety hover:text-safety disabled:opacity-40"
              >
                <Plus className="size-3.5" />
                Add box
              </button>
              {addOpen && (
                <div className="absolute right-0 top-full z-40 mt-1 flex min-w-28 flex-col rounded-sm border border-border bg-panel p-1">
                  {["door", "window", "room", "column", "stair"].map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      onClick={() => {
                        addDetection(kind);
                        setAddOpen(false);
                      }}
                      className="rounded-sm px-2 py-1 text-left font-mono text-[0.68rem] text-foreground capitalize hover:bg-safety/10 hover:text-safety"
                    >
                      {kind}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close blueprint"
              className="mr-1 inline-flex h-8 items-center gap-1.5 rounded-sm border border-border px-2 font-mono text-[0.68rem] text-foreground hover:border-safety hover:text-safety"
            >
              <X className="size-3.5" />
              Close
            </button>
          )}
          {sourceToggle && (
            <button
              type="button"
              onClick={sourceToggle.onToggle}
              className="mr-1 rounded-sm border border-border px-2 py-1 font-mono text-[0.65rem] tracking-wide text-muted-foreground uppercase hover:border-muted-foreground hover:text-foreground"
            >
              {sourceToggle.showingOriginal ? "Simplified" : "Original"}
            </button>
          )}
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

          {natural && showBoxes &&
            detections.map((d, i) => ({ d, i })).sort((a, b) => paintRank(a.d.tag) - paintRank(b.d.tag)).map(({ d, i }) => {
              const [ymin, xmin, ymax, xmax] = d.box;
              const active = highlighted === i;
              const paint = markPaint(d.tag);
              const weight = detectionKind(d.tag) === "room" ? 3 : 2;
              return (
                <div
                  key={i}
                  role="group"
                  aria-label={`${d.tag}${d.label ? `: ${d.label}` : ""}`}
                  title="Drag to move"
                  onPointerEnter={() => onHoverDetection(i)}
                  onPointerLeave={() => onHoverDetection(null)}
                  onPointerDown={(event) => {
                    if (analyzing || event.button !== 0 || !onMoveDetection) return;
                    event.stopPropagation();
                    boxDrag.current = { id: event.pointerId, index: i, sx: event.clientX, sy: event.clientY, box: d.box, moved: false, corner: null };
                  }}
                  className={cn(
                    "group absolute cursor-grab rounded-[1px]",
                    paint.box,
                    paint.dashed ? "border-dashed" : "border-solid",
                    active ? "z-20 animate-box-pulse" : "z-10",
                  )}
                  style={{
                    top: `${ymin / 10}%`,
                    left: `${xmin / 10}%`,
                    height: `${(ymax - ymin) / 10}%`,
                    width: `${(xmax - xmin) / 10}%`,
                    borderWidth: `calc(${active ? weight + 1 : weight}px / var(--z))`,
                    zIndex: active ? 20 : 10 + paintRank(d.tag),
                  }}
                >
                  <span
                    className={cn(
                      "pointer-events-none absolute bottom-full left-0 origin-bottom-left font-mono text-[11px] leading-none font-semibold whitespace-nowrap",
                      active ? "bg-safety text-safety-foreground" : paint.badge,
                    )}
                    style={{
                      transform: `translate(calc(-${active ? weight + 1 : weight}px / var(--z)), 0) scale(calc(1 / var(--z)))`,
                      padding: "3px 5px",
                    }}
                  >
                    {d.tag}
                  </span>
                  {onMoveDetection &&
                    BOX_HANDLES.map((handle) => (
                      <button
                        key={handle.corner}
                        type="button"
                        aria-label={`Resize ${d.tag} ${handle.corner}`}
                        title="Drag to resize"
                        onPointerDown={(event) => {
                          if (analyzing || event.button !== 0) return;
                          event.stopPropagation();
                          boxDrag.current = {
                            id: event.pointerId,
                            index: i,
                            sx: event.clientX,
                            sy: event.clientY,
                            box: d.box,
                            moved: false,
                            corner: handle.corner,
                          };
                        }}
                        className={cn(
                          "absolute z-30 size-2.5 rounded-[1px] border border-foreground bg-background opacity-0 group-hover:opacity-100",
                          handle.place,
                          handle.cursor,
                          active && "opacity-100",
                        )}
                        style={{ transform: `translate(${handle.shift}) scale(calc(1 / var(--z)))` }}
                      />
                    ))}
                  {onDeleteDetection && (
                    <button
                      type="button"
                      aria-label={`Remove ${d.tag}`}
                      title="Remove this box"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeleteDetection(i);
                      }}
                      className={cn(
                        "absolute top-0 right-0 z-30 inline-flex size-5 origin-top-right items-center justify-center rounded-sm bg-background text-foreground opacity-0 group-hover:opacity-100",
                        active && "opacity-100",
                      )}
                      style={{ transform: "translate(40%, -40%) scale(calc(1 / var(--z)))" }}
                    >
                      <X className="size-3" />
                    </button>
                  )}
                </div>
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

        {showBoxes && detections.length > 0 && (
          <p className="pointer-events-none absolute top-3 left-1/2 z-20 max-w-[70%] -translate-x-1/2 rounded-sm border border-border bg-panel/90 px-2.5 py-1.5 text-center text-xs leading-relaxed text-muted-foreground backdrop-blur">
            If we got one wrong, drag the box, pull a corner, or remove it.
          </p>
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
          <div className="pointer-events-none absolute right-3 bottom-3 flex max-w-[70%] flex-wrap items-center justify-end gap-1.5 rounded-sm border border-border bg-panel/90 px-2.5 py-1.5 font-mono text-[0.7rem] text-foreground backdrop-blur">
            {legendKinds(detections).map((kind) => (
              <span key={kind} className="inline-flex items-center gap-1">
                <span className={cn("size-2.5", markPaint(kind).swatch, markPaint(kind).dashed && "border border-dashed border-foreground")} />
                {kind}
              </span>
            ))}
            <span className="text-muted-foreground">{kindSummary(detections)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function paintRank(tag: string): number {
  const order = ["room", "stair", "column", "door", "window"];
  const rank = order.indexOf(detectionKind(tag));
  return rank === -1 ? order.length : rank;
}

function legendKinds(detections: Detection[]): string[] {
  const seen: string[] = [];
  for (const item of [...detections].sort((a, b) => paintRank(a.tag) - paintRank(b.tag))) {
    const kind = detectionKind(item.tag);
    const title = kind.charAt(0).toUpperCase() + kind.slice(1);
    if (!seen.includes(title)) seen.push(title);
  }
  return seen;
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
  return ACCEPTED_TYPES.includes(file.type);
}
