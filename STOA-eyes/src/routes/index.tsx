import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FolderUp, ImagePlus } from "lucide-react";
import { toast } from "sonner";

import sampleApartment from "@/assets/sample-apartment.jpg";
import sampleOffice from "@/assets/sample-office.jpg";
import swissFloor from "@/proofs/swiss-floor.png";
import swissProof from "@/proofs/swiss-floor.json";
import sampleSchedule from "../../sample-project/schedule.csv?raw";
import sampleNotes from "../../sample-project/site-meeting.txt?raw";
import sampleBlueprint from "../../sample-project/A-201 Office 1.jpg";
import { ChatPanel, type ChatMessage } from "@/components/stoa/ChatPanel";
import { DrawingCanvas, isAcceptedFile, type Drawing, type DrawingCanvasHandle } from "@/components/stoa/DrawingCanvas";
import { ProjectCheckPanel } from "@/components/stoa/ProjectCheckPanel";
import { checkProject, type ProjectReport } from "@/lib/project-check";
import { readProjectFiles } from "@/lib/project-files";
import { normalizeAnalysis, type RawAnalysis } from "@/lib/detections";
import { routeQuestion } from "@/lib/checker";
import { prepareImageForAnalysis, type PreparedImage } from "@/lib/image-prep";
import { analyzeDrawing, backendStatus } from "@/lib/vision.functions";
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
  { id: "proof-swiss", name: "Swiss · site 1000", src: swissFloor, kind: "sample" },
  { id: "sample-apartment", name: "A-101 · 2BR Apartment", src: sampleApartment, kind: "sample" },
  { id: "sample-office", name: "A-201 · Office Level 1", src: sampleOffice, kind: "sample" },
];

function swissSheetProof(question: string): RawAnalysis | null {
  const routed = routeQuestion(question);
  if (routed.template === "label_count") {
    return {
      answer: `${swissProof.value} labels on this sheet. Each box is the printed word.`,
      object_type: "Label",
      count: swissProof.value,
      verdict: "unverified",
      warning: swissProof.note,
      items: swissProof.items.map((item) => ({ ...item, note: "text box" })),
    };
  }
  if (routed.template === "room_area") {
    const polygon = swissProof.room.polygon as [number, number][];
    const xs = polygon.map((point) => point[0]);
    const ys = polygon.map((point) => point[1]);
    return {
      answer: "Room 2.10. Polygon. The warning says whether the written scale and the printed areas agree.",
      object_type: "Room",
      count: 1,
      verdict: "unverified",
      warning: swissProof.scale === "agrees" ? "The written scale and the printed areas agree." : "Low confidence: the two scale factors disagree.",
      items: [
        {
          label: swissProof.room.label,
          note: "polygon",
          page: swissProof.room.page,
          polygon,
          xmin: Math.min(...xs),
          ymin: Math.min(...ys),
          xmax: Math.max(...xs),
          ymax: Math.max(...ys),
        },
      ],
    };
  }
  return null;
}

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
  const [mode, setMode] = useState<"check" | "qa">("qa");
  const [report, setReport] = useState<ProjectReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [backendNote, setBackendNote] = useState("Backend starting");

  const canvasRef = useRef<DrawingCanvasHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const projectInput = useRef<HTMLInputElement>(null);
  const prepared = useRef<Map<string, PreparedImage>>(new Map());

  const activeMessage = messages.find((m) => m.id === activeMessageId);
  const detections = activeMessage?.role === "assistant" && activeMessage.status === "done" ? activeMessage.result.detections : [];

  useEffect(() => {
    void backendStatus()
      .then((status) => setBackendNote(status.label))
      .catch(() => setBackendNote("Backend unavailable"));
  }, []);

  useEffect(() => {
    setHighlighted(null);
    const last = [...(threads[drawing.id] ?? [])].reverse().find((m) => m.role === "assistant" && m.status === "done");
    setActiveMessageId(last?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing.id]);

  const updateThread = (id: string, fn: (msgs: ChatMessage[]) => ChatMessage[]) =>
    setThreads((t) => ({ ...t, [id]: fn(t[id] ?? []) }));

  const handleProject = useCallback(async (list: FileList | File[]) => {
    const files = Array.from(list);
    if (!files.length) return;
    const images = files.filter(isAcceptedFile);
    const known = new Set(drawings.map((item) => item.name));
    const created: Drawing[] = images
      .filter((file) => !known.has(file.name))
      .map((file) => ({
        id: `upload-${uid()}`,
        name: file.name,
        src: URL.createObjectURL(file),
        kind: "upload",
      }));
    if (created.length) {
      setDrawings((ds) => [...ds, ...created]);
      setDrawingId(created[0]!.id);
    }
    setMode("check");
    setChecking(true);
    try {
      setReport(checkProject(await readProjectFiles(files)));
    } catch (error) {
      console.error(error);
      toast.error("Project check failed", { description: "One of the files could not be read." });
    } finally {
      setChecking(false);
    }
  }, [drawings]);

  const loadSampleProject = useCallback(async () => {
    const image = await fetch(sampleBlueprint).then((response) => response.blob());
    await handleProject([
      new File([sampleSchedule], "schedule.csv", { type: "text/csv" }),
      new File([sampleNotes], "site-meeting.txt", { type: "text/plain" }),
      new File([image], "A-201 Office 1.jpg", { type: "image/jpeg" }),
    ]);
  }, [handleProject]);

  const openBlueprint = (filename: string) => {
    const found = drawings.find((item) => item.name === filename);
    if (found) setDrawingId(found.id);
  };

  const handleFiles = useCallback((files: FileList | File[]) => {
    const file = Array.from(files)[0];
    if (!file) return;
    if (!isAcceptedFile(file)) {
      toast.error("Unsupported file", { description: "Upload a PNG, JPG, WebP, PDF or IFC drawing." });
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    const structured = /\.(pdf|ifc)$/i.test(file.name);
    const d: Drawing = {
      id: `upload-${uid()}`,
      name: file.name,
      src: structured ? "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" : objectUrl,
      fileUrl: objectUrl,
      kind: "upload",
    };
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
      const structured = /\.(pdf|ifc)$/i.test(target.name);
      let dataUrl: string;
      let imageWidth = 1;
      let imageHeight = 1;
      if (structured) {
        const blob = await fetch(target.fileUrl || target.src).then((response) => response.blob());
        dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(blob);
        });
      } else {
        let img = prepared.current.get(target.id);
        if (!img) {
          img = await prepareImageForAnalysis(target.src);
          prepared.current.set(target.id, img);
        }
        dataUrl = img.dataUrl;
        imageWidth = img.width;
        imageHeight = img.height;
      }
      const res = await analyzeDrawing({
        data: {
          imageDataUrl: dataUrl,
          imageWidth,
          imageHeight,
          question,
          filename: target.name,
          history,
        },
      });
      if (!res.ok) {
        updateThread(target.id, (msgs) =>
          msgs.map((m) => (m.id === pendingId ? { id: pendingId, role: "assistant", status: "error", error: res.error } : m)),
        );
        return;
      }
      const sheet = target.id === "proof-swiss" ? swissSheetProof(question) : null;
      const result = normalizeAnalysis(sheet ?? res.raw);
      if (res.previewDataUrl) {
        setDrawings((ds) => ds.map((item) => (item.id === target.id ? { ...item, src: res.previewDataUrl! } : item)));
      }
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
    updateThread(drawing.id, (msgs) =>
      msgs.map((m) => {
        if (m.id !== messageId || m.role !== "assistant" || m.status !== "done") return m;
        const targetBox = m.result.detections[index];
        if (!targetBox?.disputed) return m;
        const detections = m.result.detections.map((d, i) =>
          i === index ? { ...d, included: d.included === false } : d,
        );
        const count = detections.filter((d) => d.included !== false).length;
        return { ...m, result: { ...m.result, detections, count } };
      }),
    );
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
          onClick={() => projectInput.current?.click()}
          className="inline-flex shrink-0 items-center gap-2 rounded-sm border border-safety bg-safety/10 px-3 py-1.5 font-display text-sm font-semibold text-foreground transition-colors hover:bg-safety/20"
        >
          <FolderUp className="size-4 text-safety" />
          Upload project
        </button>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="inline-flex shrink-0 items-center gap-2 rounded-sm bg-primary px-3 py-1.5 font-display text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <ImagePlus className="size-4" />
          Upload drawing
        </button>
        <input
          ref={projectInput}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.webp,.pdf,.xlsx,.csv,.txt,.md,.docx,image/png,image/jpeg,image/webp,application/pdf,text/plain,text/csv"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) void handleProject(e.target.files);
            e.target.value = "";
          }}
        />
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
        <aside className="flex min-h-0 flex-1 flex-col border-t border-border lg:w-[30%] lg:flex-none lg:border-t-0" aria-label="Project tools">
          <div className="flex h-10 shrink-0 border-b border-border bg-background">
            <button
              type="button"
              onClick={() => setMode("check")}
              className={cn(
                "flex-1 font-display text-sm font-semibold tracking-wide",
                mode === "check" ? "bg-safety/10 text-safety" : "text-muted-foreground hover:text-foreground",
              )}
            >
              Project Check
            </button>
            <button
              type="button"
              onClick={() => setMode("qa")}
              className={cn(
                "flex-1 border-l border-border font-display text-sm font-semibold tracking-wide",
                mode === "qa" ? "bg-safety/10 text-safety" : "text-muted-foreground hover:text-foreground",
              )}
            >
              Drawing Q&A
            </button>
          </div>
          <div className="min-h-0 flex-1">
          {mode === "check" ? (
            <ProjectCheckPanel
              report={report}
              checking={checking}
              onOpenBlueprint={openBlueprint}
              onLoadSample={() => void loadSampleProject()}
            />
          ) : (
          <ChatPanel
            messages={messages}
            busy={busy}
            activeMessageId={activeMessageId}
            highlighted={highlighted}
            showBoxes={showBoxes}
            backendNote={backendNote}
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
          )}
          </div>
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
