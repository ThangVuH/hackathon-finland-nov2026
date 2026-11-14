import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ImagePlus } from "lucide-react";
import { toast } from "sonner";

import { ChatPanel, type ChatMessage } from "@/components/stoa/ChatPanel";
import { DrawingCanvas, isAcceptedFile, type Drawing, type DrawingCanvasHandle } from "@/components/stoa/DrawingCanvas";
import { normalizeAnalysis, stabilizeDetections } from "@/lib/detections";
import { prepareImageForAnalysis, type PreparedImage } from "@/lib/image-prep";
import { detectSheetMarks } from "@/lib/sketch-mark";
import { selectDrawingTargets } from "@/lib/file-target";
import { offTopicReply } from "@/lib/off-topic";
import { analyzeDrawing, simplifyDrawing } from "@/lib/vision.functions";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "BlueprintEye — AI drawing analysis for site engineers" },
      {
        name: "description",
        content: "Ask questions about one or more construction drawings and read each count with the file it came from.",
      },
      { property: "og:title", content: "BlueprintEye — AI drawing analysis for site engineers" },
      {
        property: "og:description",
        content: "Count doors, windows, rooms and columns on construction drawings. Each answer names the file.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: StoaVision,
});

const uid = () => Math.random().toString(36).slice(2, 10);

type SheetPhase = "reading" | "simplifying" | "original" | "simplified";
interface SheetView {
  phase: SheetPhase;
  src?: string;
  note?: string;
}

function Wordmark() {
  const [showAi, setShowAi] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setShowAi((current) => !current), 3000);
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="font-display text-[1.541rem] font-bold leading-none tracking-[0.12em]">
      <span className="sr-only">Blueprint.Eye</span>
      <span aria-hidden>
        Blueprint<span className="text-white">.</span>
        <span className="inline-grid justify-items-start text-safety">
          <span className={cn("col-start-1 row-start-1 transition-opacity duration-500", showAi ? "opacity-0" : "opacity-100")}>Eye</span>
          <span className={cn("col-start-1 row-start-1 transition-opacity duration-500", showAi ? "opacity-100" : "opacity-0")}>AI</span>
        </span>
      </span>
    </span>
  );
}

function StoaVision() {
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const [showBlueprint, setShowBlueprint] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sheets, setSheets] = useState<Record<string, SheetView>>({});

  const canvasRef = useRef<DrawingCanvasHandle>(null);
  const prepared = useRef<Map<string, PreparedImage>>(new Map());
  const ready = useRef<Map<string, Promise<void>>>(new Map());

  const drawing = drawings.find((item) => item.id === activeId) ?? drawings[0] ?? null;
  const highlighted = hovered ?? pinned;
  const sheet = drawing ? sheets[drawing.id] : undefined;
  const simplifiedSrc = sheet?.phase === "simplified" ? sheet.src : undefined;
  const displaySrc = drawing && !showOriginal && simplifiedSrc ? simplifiedSrc : drawing?.src;
  const activeDone = messages.find((message) => message.id === activeMessageId);
  const resultMessage =
    activeDone?.role === "assistant" && activeDone.status === "done" && activeDone.fileId === drawing?.id
      ? activeDone
      : [...messages].reverse().find((message) => message.role === "assistant" && message.status === "done" && message.fileId === drawing?.id);
  const detections = resultMessage?.role === "assistant" && resultMessage.status === "done" ? resultMessage.result.detections : [];

  useEffect(() => {
    for (const drawing of drawings) {
      if (ready.current.has(drawing.id)) continue;
      const id = drawing.id;
      const src = drawing.src;
      const job = (async () => {
        setSheets((current) => ({ ...current, [id]: { phase: "reading" } }));
        try {
          const marks = await detectSheetMarks(src);
          const original = await prepareImageForAnalysis(src);
          if (!marks.complicated) {
            prepared.current.set(id, original);
            setSheets((current) => ({ ...current, [id]: { phase: "original" } }));
            return;
          }
          setSheets((current) => ({ ...current, [id]: { phase: "simplifying" } }));
          const simplified = await simplifyDrawing({
            data: { imageDataUrl: original.dataUrl, imageWidth: original.width, imageHeight: original.height },
          });
          if (!simplified.ok) {
            prepared.current.set(id, original);
            setSheets((current) => ({ ...current, [id]: { phase: "original" } }));
            return;
          }
          const redraw = await prepareImageForAnalysis(simplified.imageDataUrl);
          prepared.current.set(id, redraw);
          setSheets((current) => ({ ...current, [id]: { phase: "simplified", src: redraw.dataUrl, note: simplified.note } }));
        } catch (error) {
          console.error(error);
          try {
            prepared.current.set(id, await prepareImageForAnalysis(src));
          } catch {
            prepared.current.delete(id);
          }
          setSheets((current) => ({ ...current, [id]: { phase: "original" } }));
        }
      })();
      ready.current.set(id, job);
    }
  }, [drawings]);

  const handleFiles = useCallback((files: FileList | File[]) => {
    const accepted: Drawing[] = [];
    for (const file of Array.from(files)) {
      if (!isAcceptedFile(file)) {
        toast.error("Unsupported file", { description: `${file.name} is not a PNG, JPG, or WebP drawing.` });
        continue;
      }
      accepted.push({ id: `upload-${uid()}`, name: file.name, src: URL.createObjectURL(file), kind: "upload" });
    }
    if (accepted.length === 0) return;
    setDrawings((current) => [...current, ...accepted]);
    setActiveId((current) => current ?? accepted[0]!.id);
  }, []);

  const removeFile = useCallback((id: string) => {
    setDrawings((current) => {
      const found = current.find((drawing) => drawing.id === id);
      if (found) URL.revokeObjectURL(found.src);
      return current.filter((drawing) => drawing.id !== id);
    });
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setActiveMessageId(null);
    setHovered(null);
    setPinned(null);
  }, []);

  const clearFiles = useCallback(() => {
    setDrawings((current) => {
      for (const item of current) URL.revokeObjectURL(item.src);
      return [];
    });
    setActiveId(null);
    setShowBlueprint(false);
    prepared.current.clear();
    ready.current.clear();
    setSheets({});
  }, []);

  const ask = async (question: string) => {
    const aside = offTopicReply(question);
    if (aside) {
      setMessages((current) => [
        ...current,
        { id: uid(), role: "user", text: question, files: [] },
        { id: uid(), role: "assistant", status: "note", text: aside },
      ]);
      return;
    }
    if (drawings.length === 0) {
      toast.error("Add a drawing first");
      return;
    }
    const selection = selectDrawingTargets(question, drawings, activeId);
    if (selection.kind === "missing") {
      setMessages((current) => [
        ...current,
        { id: uid(), role: "user", text: question, files: [] },
        { id: uid(), role: "assistant", status: "note", text: selection.reply },
      ]);
      return;
    }
    if (selection.kind === "choose") {
      const userMessageId = uid();
      setMessages((current) => [
        ...current,
        { id: userMessageId, role: "user", text: question, files: [] },
        { id: uid(), role: "assistant", status: "choose", question, files: selection.files, userMessageId },
      ]);
      return;
    }
    const targets = drawings.filter((item) => selection.files.some((file) => file.id === item.id));
    await runOnFiles(question, targets, true);
  };

  const chooseDrawings = (userMessageId: string, question: string, ids: string[]) => {
    const targets = drawings.filter((item) => ids.includes(item.id));
    void runOnFiles(question, targets, false, userMessageId);
  };

  const runOnFiles = async (question: string, targets: Drawing[], recordUser: boolean, userMessageId?: string) => {
    if (targets.length === 0) return;
    const named = targets.map((drawing) => ({ id: drawing.id, name: drawing.name }));
    const pending = targets.map((drawing) => ({ id: uid(), drawing }));
    const prior = messages;
    setMessages((current) => [
      ...current.map((message) => {
        if (message.role === "user" && message.id === userMessageId) return { ...message, files: named };
        if (message.role === "assistant" && message.status === "choose" && message.userMessageId === userMessageId) return { ...message, chosen: true };
        return message;
      }),
      ...(recordUser ? [{ id: uid(), role: "user" as const, text: question, files: named }] : []),
      ...pending.map((item) => ({ id: item.id, role: "assistant" as const, status: "pending" as const, fileId: item.drawing.id, fileName: item.drawing.name })),
    ]);
    setBusy(true);
    try {
      for (const item of pending) {
        await answerFile(item.drawing, item.id, question, prior);
      }
    } finally {
      setBusy(false);
    }
  };

  const answerFile = async (target: Drawing, pendingId: string, question: string, prior: ChatMessage[]) => {
    const history = prior.flatMap((message): { role: "user" | "assistant"; text: string }[] => {
      if (message.role === "user") {
        return message.files.some((file) => file.id === target.id) ? [{ role: "user", text: message.text }] : [];
      }
      return message.fileId === target.id && message.status === "done" ? [{ role: "assistant", text: summarize(message.result) }] : [];
    });
    const known = prior.flatMap((message) =>
      message.role === "assistant" && message.fileId === target.id && message.status === "done" ? message.result.detections : [],
    );
    const fail = (error: string) =>
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId ? { id: pendingId, role: "assistant", status: "error", error, fileId: target.id, fileName: target.name } : message,
        ),
      );
    try {
      await ready.current.get(target.id);
      let img = prepared.current.get(target.id);
      if (!img) {
        img = await prepareImageForAnalysis(target.src);
        prepared.current.set(target.id, img);
      }
      const res = await analyzeDrawing({
        data: {
          imageDataUrl: img.dataUrl,
          imageWidth: img.width,
          imageHeight: img.height,
          question,
          sheetName: target.name,
          history,
        },
      });
      if (!res.ok) {
        fail(res.error);
        return;
      }
      const result = stabilizeDetections(known, normalizeAnalysis(res.raw));
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId
            ? { id: pendingId, role: "assistant", status: "done", result, fileId: target.id, fileName: target.name }
            : message,
        ),
      );
      setActiveId(target.id);
      setActiveMessageId(pendingId);
      setHovered(null);
      setPinned(null);
    } catch (err) {
      console.error(err);
      fail("Couldn't reach the analysis service. Check your connection and try again.");
    }
  };

  const selectItem = (messageId: string, index: number) => {
    const message = messages.find((item) => item.id === messageId);
    if (message?.role === "assistant") setActiveId(message.fileId);
    setActiveMessageId(messageId);
    setPinned(index);
    setShowBlueprint(true);
    requestAnimationFrame(() => canvasRef.current?.focusDetection(index));
  };

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-background px-4">
        <div className="flex items-center gap-2.5">
          <div className="hazard-stripe size-[1.7125rem] rounded-[2px]" aria-hidden />
          <Wordmark />
        </div>
      </header>
      <input
        id="drawing-files"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        className="hidden"
        onChange={(event) => {
          if (event.target.files) handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <main className="relative flex min-h-0 flex-1 flex-col bg-canvas lg:flex-row">
        {showBlueprint && (
          <section
            className={cn(
              "min-h-0 border-border",
              chatOpen ? "h-[55vh] lg:h-auto lg:w-[70%] lg:border-r" : "flex-1",
            )}
            aria-label="Drawing canvas"
          >
            {drawing && displaySrc ? (
              <DrawingCanvas
                handleRef={canvasRef}
                drawing={{ ...drawing, src: displaySrc }}
                detections={showOriginal ? [] : detections}
                showBoxes={!showOriginal}
                highlighted={highlighted}
                analyzing={busy || sheet?.phase === "simplifying"}
                sourceToggle={
                  simplifiedSrc
                    ? { showingOriginal: showOriginal, onToggle: () => setShowOriginal((value) => !value) }
                    : null
                }
                onClose={chatOpen ? () => setShowBlueprint(false) : undefined}
                onHoverDetection={setHovered}
                onSelectDetection={(index) => activeMessageId && selectItem(activeMessageId, index)}
                onFiles={handleFiles}
              />
            ) : (
              <EmptySheet onUpload={() => document.getElementById("drawing-files")?.click()} onFiles={handleFiles} />
            )}
          </section>
        )}
        {chatOpen && (
        <aside className={cn("flex min-h-0 w-full flex-1 flex-col bg-canvas", showBlueprint && "border-t border-border lg:w-[30%] lg:flex-none lg:border-t-0")} aria-label="Drawing Q&A">
          <ChatPanel
            messages={messages}
            files={drawings.map((item) => ({ id: item.id, name: item.name }))}
            busy={busy}
            horizontal={!showBlueprint}
            showBlueprint={showBlueprint}
            onToggleBlueprint={(messageId) => {
              const message = messages.find((item) => item.id === messageId);
              if (!message || message.role !== "assistant" || message.status !== "done") return;
              if (showBlueprint && activeMessageId === messageId) {
                setShowBlueprint(false);
                return;
              }
              setActiveId(message.fileId);
              setActiveMessageId(messageId);
              setShowOriginal(false);
              setPinned(null);
              setHovered(null);
              setShowBlueprint(true);
            }}
            activeFileId={drawing?.id ?? null}
            activeMessageId={activeMessageId}
            highlighted={highlighted}
            onAddFiles={handleFiles}
            onRemoveFile={removeFile}
            onClearFiles={clearFiles}
            onClearMessages={clearMessages}
            onOpenFile={(id) => {
              if (showBlueprint && drawing?.id === id) {
                setShowBlueprint(false);
                return;
              }
              setActiveId(id);
              setShowOriginal(false);
              setShowBlueprint(true);
              const last = [...messages].reverse().find((message) => message.role === "assistant" && message.status === "done" && message.fileId === id);
              setActiveMessageId(last?.id ?? null);
              setPinned(null);
              setHovered(null);
            }}
            onAsk={ask}
            onChoose={chooseDrawings}
            onHoverItem={(id, index) => {
              const message = messages.find((item) => item.id === id);
              if (message?.role === "assistant") setActiveId(message.fileId);
              setActiveMessageId(id);
              setHovered(index);
            }}
            onSelectItem={selectItem}
          />
        </aside>
        )}
        {!chatOpen && (
          <button
            type="button"
            onClick={() => {
              setShowBlueprint(false);
              setChatOpen(true);
            }}
            aria-label="Open chat"
            className="absolute bottom-8 left-1/2 z-20 inline-flex size-12 -translate-x-1/2 animate-bounce items-center justify-center rounded-full border border-safety bg-canvas text-safety"
          >
            <ChevronDown className="size-6" />
          </button>
        )}
      </main>
    </div>
  );
}

function EmptySheet({ onUpload, onFiles }: { onUpload: () => void; onFiles: (files: FileList | File[]) => void }) {
  const [dropActive, setDropActive] = useState(false);
  return (
    <div
      className="relative flex h-full min-h-0 flex-col bg-canvas"
      onDragOver={(event) => {
        event.preventDefault();
        setDropActive(true);
      }}
      onDragLeave={() => setDropActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDropActive(false);
        if (event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
      }}
    >
      <button
        type="button"
        onClick={onUpload}
        className={cn("flex min-h-0 flex-1 flex-col items-center justify-center gap-8 bg-blueprint-grid px-8", dropActive && "bg-safety/10")}
      >
        <div className="pointer-events-none">
          <p className="font-display text-[0.975rem] tracking-[0.42em] text-muted-foreground">You ask</p>
          <p className="mt-[0.975rem] font-display text-[4.875rem] leading-none font-bold tracking-[0.18em] text-safety">Blueprints</p>
          <p className="mt-[0.975rem] font-display text-[0.975rem] tracking-[0.42em] text-foreground">respond</p>
          <div className="mx-auto mt-[1.95rem] h-px w-[6.5rem] bg-safety" aria-hidden />
          <p className="mx-auto mt-[1.95rem] max-w-md text-[1.3rem] leading-relaxed text-muted-foreground">
            We detect doors, windows, rooms, and columns on the sheet
          </p>
        </div>
        <span className="inline-flex items-center gap-2 font-display text-sm text-foreground">
          <ImagePlus className="size-4 text-safety" />
          {dropActive ? "Drop the files" : "Upload a drawing"}
          <span className="label-tech">PNG · JPG · WEBP</span>
        </span>
      </button>
    </div>
  );
}

function summarize(r: ReturnType<typeof normalizeAnalysis>) {
  if (!r.detections.length) return r.answer;
  const list = r.detections.map((d) => `${d.tag}${d.label ? ` (${d.label})` : ""} [${d.box.join(",")}]`).join("; ");
  return `${r.answer}\nDetected ${r.count} ${r.objectType}(s): ${list}`;
}
