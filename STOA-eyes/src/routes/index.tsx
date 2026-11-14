import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { toast } from "sonner";

import sampleApartment from "@/assets/sample-apartment.jpg";
import sampleOffice from "@/assets/sample-office.jpg";
import { ChatPanel, type ChatMessage } from "@/components/stoa/ChatPanel";
import { DrawingCanvas, isAcceptedFile, type Drawing, type DrawingCanvasHandle } from "@/components/stoa/DrawingCanvas";
import { normalizeAnalysis } from "@/lib/detections";
import { prepareImageForAnalysis, type PreparedImage } from "@/lib/image-prep";
import { analyzeDrawing } from "@/lib/vision.functions";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Stoa Vision — AI drawing analysis for site engineers" },
      {
        name: "description",
        content: "Ask questions about construction drawings and verify every AI count with numbered bounding boxes on the sheet.",
      },
      { property: "og:title", content: "Stoa Vision — AI drawing analysis for site engineers" },
      {
        property: "og:description",
        content: "Count doors, windows, rooms and columns on construction drawings — and verify each one visually.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: StoaVision,
});

const SAMPLES: Drawing[] = [
  { id: "sample-apartment", name: "A-101 · 2BR Apartment", src: sampleApartment, kind: "sample" },
  { id: "sample-office", name: "A-201 · Office Level 1", src: sampleOffice, kind: "sample" },
];

const uid = () => Math.random().toString(36).slice(2, 10);

function StoaVision() {
  const [drawings, setDrawings] = useState<Drawing[]>(SAMPLES);
  const [drawingId, setDrawingId] = useState(SAMPLES[0]!.id);
  const drawing = drawings.find((d) => d.id === drawingId) ?? SAMPLES[0]!;

  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({});
  const messages = threads[drawing.id] ?? [];
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const highlighted = hovered ?? pinned;
  const setHighlighted = (i: number | null) => {
    setHovered(null);
    setPinned(i);
  };
  const [showBoxes, setShowBoxes] = useState(true);
  const [busy, setBusy] = useState(false);

  const canvasRef = useRef<DrawingCanvasHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const prepared = useRef<Map<string, PreparedImage>>(new Map());

  const activeMessage = messages.find((m) => m.id === activeMessageId);
  const detections = activeMessage?.role === "assistant" && activeMessage.status === "done" ? activeMessage.result.detections : [];

  useEffect(() => {
    setHighlighted(null);
    const last = [...(threads[drawing.id] ?? [])].reverse().find((m) => m.role === "assistant" && m.status === "done");
    setActiveMessageId(last?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing.id]);

  const updateThread = (id: string, fn: (msgs: ChatMessage[]) => ChatMessage[]) =>
    setThreads((t) => ({ ...t, [id]: fn(t[id] ?? []) }));

  const handleFiles = useCallback((files: FileList | File[]) => {
    const file = Array.from(files)[0];
    if (!file) return;
    if (!isAcceptedFile(file)) {
      toast.error("Unsupported file", { description: "Upload a PNG, JPG or WebP drawing." });
      return;
    }
    const d: Drawing = { id: `upload-${uid()}`, name: file.name, src: URL.createObjectURL(file), kind: "upload" };
    setDrawings((ds) => [...ds, d]);
    setDrawingId(d.id);
  }, []);

  const ask = async (question: string) => {
    const target = drawing;
    const history = messages.flatMap((m): { role: "user" | "assistant"; text: string }[] =>
      m.role === "user"
        ? [{ role: "user", text: m.text }]
        : m.status === "done"
          ? [{ role: "assistant", text: summarize(m.result) }]
          : [],
    );
    const pendingId = uid();
    updateThread(target.id, (msgs) => [
      ...msgs,
      { id: uid(), role: "user", text: question },
      { id: pendingId, role: "assistant", status: "pending" },
    ]);
    setBusy(true);
    try {
      let img = prepared.current.get(target.id);
      if (!img) {
        img = await prepareImageForAnalysis(target.src);
        prepared.current.set(target.id, img);
      }
      const res = await analyzeDrawing({
        data: { imageDataUrl: img.dataUrl, imageWidth: img.width, imageHeight: img.height, question, history },
      });
      if (!res.ok) {
        updateThread(target.id, (msgs) =>
          msgs.map((m) => (m.id === pendingId ? { id: pendingId, role: "assistant", status: "error", error: res.error } : m)),
        );
        return;
      }
      const result = normalizeAnalysis(res.raw);
      updateThread(target.id, (msgs) =>
        msgs.map((m) => (m.id === pendingId ? { id: pendingId, role: "assistant", status: "done", result } : m)),
      );
      if (result.detections.length > 0) {
        setActiveMessageId(pendingId);
        setHighlighted(null);
      }
    } catch (err) {
      console.error(err);
      updateThread(target.id, (msgs) =>
        msgs.map((m) =>
          m.id === pendingId
            ? { id: pendingId, role: "assistant", status: "error", error: "Couldn't reach the analysis service. Check your connection and try again." }
            : m,
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const selectDetection = (messageId: string, index: number) => {
    setActiveMessageId(messageId);
    setPinned(index);
    setShowBoxes(true);
    // Wait for the active message's boxes to render before focusing.
    requestAnimationFrame(() => canvasRef.current?.focusDetection(index));
  };

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      {/* Top bar */}
      <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-background px-4">
        <div className="flex items-center gap-2.5">
          <div className="hazard-stripe size-5 rounded-[2px]" aria-hidden />
          <span className="font-display text-lg font-bold tracking-[0.12em]">
            Stoa <span className="text-safety">Vision</span>
          </span>
        </div>
        <div className="h-5 w-px bg-border" />
        <nav className="scrollbar-thin flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto" aria-label="Drawings">
          {drawings.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => setDrawingId(d.id)}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-sm border px-2.5 py-1 font-mono text-[0.72rem] transition-colors",
                d.id === drawing.id
                  ? "border-safety bg-safety/10 text-foreground"
                  : "border-border text-muted-foreground hover:border-muted-foreground hover:text-foreground",
              )}
            >
              <span className={cn("text-[0.6rem]", d.kind === "sample" ? "text-scan" : "text-safety")}>
                {d.kind === "sample" ? "SAMPLE" : "UPLOAD"}
              </span>
              <span className="max-w-44 truncate">{d.name}</span>
            </button>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="inline-flex shrink-0 items-center gap-2 rounded-sm bg-primary px-3 py-1.5 font-display text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <ImagePlus className="size-4" />
          Upload drawing
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </header>

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section className="h-[55vh] min-h-0 border-border lg:h-auto lg:w-[70%] lg:border-r" aria-label="Drawing canvas">
          <DrawingCanvas
            handleRef={canvasRef}
            drawing={drawing}
            detections={detections}
            showBoxes={showBoxes}
            highlighted={highlighted}
            analyzing={busy}
            onHoverDetection={setHovered}
            onSelectDetection={(i) => activeMessageId && selectDetection(activeMessageId, i)}
            onFiles={handleFiles}
          />
        </section>
        <aside className="min-h-0 flex-1 border-t border-border lg:w-[30%] lg:flex-none lg:border-t-0" aria-label="Q&A">
          <ChatPanel
            messages={messages}
            busy={busy}
            activeMessageId={activeMessageId}
            highlighted={highlighted}
            showBoxes={showBoxes}
            onShowBoxesChange={setShowBoxes}
            onAsk={ask}
            onActivate={(id) => {
              setActiveMessageId(id);
              setHighlighted(null);
              setShowBoxes(true);
            }}
            onHover={(_, i) => setHovered(i)}
            onSelect={selectDetection}
          />
        </aside>
      </main>
    </div>
  );
}

function summarize(r: ReturnType<typeof normalizeAnalysis>) {
  if (!r.detections.length) return r.answer;
  const list = r.detections.map((d) => `${d.tag}${d.label ? ` (${d.label})` : ""} [${d.box.join(",")}]`).join("; ");
  return `${r.answer}\nDetected ${r.count} ${r.objectType}(s): ${list}`;
}
