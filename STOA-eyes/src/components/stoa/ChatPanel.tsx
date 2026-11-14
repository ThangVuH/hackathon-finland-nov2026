import { useEffect, useRef, useState } from "react";
import { ArrowUp, Eye, FileImage, GripVertical, Loader2, TriangleAlert, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { spokenAnswer } from "@/lib/speak";
import { detectionKind, kindSummary, type AnalysisResult } from "@/lib/detections";
import { markPaint } from "@/lib/mark-style";

export type ChatFile = { id: string; name: string };

export type ChatMessage =
  | { id: string; role: "user"; text: string; files: ChatFile[] }
  | { id: string; role: "assistant"; status: "pending"; fileId: string; fileName: string }
  | { id: string; role: "assistant"; status: "error"; error: string; fileId: string; fileName: string }
  | { id: string; role: "assistant"; status: "done"; result: AnalysisResult; fileId: string; fileName: string }
  | { id: string; role: "assistant"; status: "note"; text: string }
  | { id: string; role: "assistant"; status: "choose"; question: string; files: ChatFile[]; userMessageId: string; chosen?: boolean };

const QUICK_PROMPTS = ["How many doors?", "Count all windows", "How many rooms?", "Count the columns"];

interface Props {
  messages: ChatMessage[];
  files: ChatFile[];
  busy: boolean;
  showBlueprint: boolean;
  horizontal: boolean;
  onToggleBlueprint: (messageId: string) => void;
  activeFileId: string | null;
  activeMessageId: string | null;
  highlighted: number | null;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveFile: (id: string) => void;
  onClearFiles: () => void;
  onClearMessages: () => void;
  onOpenFile: (id: string) => void;
  onAsk: (question: string) => void;
  onChoose: (userMessageId: string, question: string, fileIds: string[]) => void;
  onHoverItem: (messageId: string, index: number | null) => void;
  onSelectItem: (messageId: string, index: number) => void;
}

export function ChatPanel({
  messages,
  files,
  busy,
  showBlueprint,
  horizontal,
  onToggleBlueprint,
  activeFileId,
  activeMessageId,
  highlighted,
  onAddFiles,
  onRemoveFile,
  onClearFiles,
  onClearMessages,
  onOpenFile,
  onAsk,
  onChoose,
  onHoverItem,
  onSelectItem,
}: Props) {
  const [input, setInput] = useState("");
  const [dropActive, setDropActive] = useState(false);
  const [fileShare, setFileShare] = useState(33);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const drag = useRef<{ x: number; share: number; width: number } | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages.length, messages.at(-1)]);

  const submit = (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    onAsk(question);
    setInput("");
  };

  const library = files.length > 0;

  return (
    <div
      className="flex h-full min-h-0 flex-row bg-canvas"
      onDragOver={(event) => {
        event.preventDefault();
        setDropActive(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setDropActive(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDropActive(false);
        if (event.dataTransfer.files.length) onAddFiles(event.dataTransfer.files);
      }}
    >
      {library && (
        <>
        <aside className={cn("flex h-full min-h-0 shrink-0 flex-col", dropActive && "bg-safety/10")} style={{ width: `${fileShare}%` }} aria-label="Drawings to read">
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-3 py-3">
            <span className="label-tech">{files.length} {files.length === 1 ? "file" : "files"}</span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                aria-label="Delete all files"
                onClick={onClearFiles}
                disabled={busy}
                className="inline-flex h-8 items-center rounded-sm border border-border px-2 font-mono text-[0.68rem] text-muted-foreground transition-colors hover:border-safety hover:text-safety disabled:opacity-40"
              >
                Delete all
              </button>
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={busy}
                className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border px-2 font-mono text-[0.68rem] text-foreground transition-colors hover:border-safety hover:text-safety disabled:opacity-40"
              >
                <FileImage className="size-3.5" />
                Add
              </button>
            </div>
          </div>
          <ul className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {files.map((file) => (
              <li key={file.id} className={cn("mb-1 flex min-w-0 items-center gap-1 rounded-sm border bg-panel-raised py-2 pr-1 pl-2", file.id === activeFileId ? "border-safety" : "border-border")}>
                <button type="button" onClick={() => onOpenFile(file.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <FileImage className="size-3.5 shrink-0 text-scan" />
                  <span className="truncate font-mono text-[0.72rem] text-foreground">{file.name}</span>
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  disabled={busy}
                  onClick={() => onRemoveFile(file.id)}
                  className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <button
          type="button"
          aria-orientation="vertical"
          aria-label="Resize file list"
          aria-valuemin={18}
          aria-valuemax={55}
          aria-valuenow={Math.round(fileShare)}
          className="group relative z-10 flex w-2 shrink-0 cursor-col-resize items-center justify-center border-0 bg-transparent p-0"
          onPointerDown={(event) => {
            const parent = event.currentTarget.parentElement;
            if (!parent) return;
            drag.current = { x: event.clientX, share: fileShare, width: parent.getBoundingClientRect().width };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const active = drag.current;
            if (!active) return;
            const next = active.share + ((event.clientX - active.x) / active.width) * 100;
            setFileShare(Math.min(55, Math.max(18, next)));
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") setFileShare((share) => Math.max(18, share - 2));
            if (event.key === "ArrowRight") setFileShare((share) => Math.min(55, share + 2));
          }}
        >
          <span className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border group-hover:bg-safety group-focus-visible:bg-safety" />
          <span className="pointer-events-none z-10 flex h-7 w-3 items-center justify-center rounded-sm border border-border bg-canvas text-muted-foreground group-hover:border-safety group-hover:text-safety">
            <GripVertical className="size-3" />
          </span>
        </button>
        </>
      )}
      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      {messages.length > 0 && (
        <div className="flex shrink-0 items-center justify-end px-3 pt-3">
          <button
            type="button"
            aria-label="Delete conversation"
            onClick={onClearMessages}
            disabled={busy}
            className="inline-flex h-8 items-center rounded-sm border border-border px-2 font-mono text-[0.68rem] text-muted-foreground transition-colors hover:border-safety hover:text-safety disabled:opacity-40"
          >
            Delete conversation
          </button>
        </div>
      )}
      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (files.length > 0 || !showBlueprint) && <EmptyState dropActive={dropActive} />}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-sm border border-border bg-panel-raised px-3 py-2 text-sm text-foreground">
                <p>{m.text}</p>
                {m.files.length > 0 && (
                  <p className="mt-1 font-mono text-[0.68rem] text-muted-foreground">{m.files.map((file) => file.name).join(" · ")}</p>
                )}
              </div>
            </div>
          ) : m.status === "note" ? (
            <div key={m.id} className="max-w-[85%] rounded-sm border border-border px-3 py-2 text-sm leading-relaxed text-foreground">
              {m.text}
            </div>
          ) : m.status === "choose" ? (
            <div key={m.id} className="max-w-[85%] rounded-sm border border-border px-3 py-3">
              <p className="text-sm leading-relaxed text-foreground">Which drawing should I read?</p>
              <div className="mt-2.5 flex flex-col gap-1.5">
                {m.files.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    disabled={busy || m.chosen}
                    onClick={() => onChoose(m.userMessageId, m.question, [file.id])}
                    className="truncate rounded-sm border border-border bg-panel-raised px-2.5 py-1.5 text-left font-mono text-[0.72rem] text-foreground hover:border-safety hover:text-safety disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {file.name}
                  </button>
                ))}
                <button
                  type="button"
                  disabled={busy || m.chosen}
                  onClick={() => onChoose(m.userMessageId, m.question, m.files.map((file) => file.id))}
                  className="rounded-sm bg-safety px-2.5 py-1.5 text-left font-mono text-[0.72rem] font-semibold text-safety-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  All of these
                </button>
              </div>
            </div>
          ) : (
            <AssistantMessage
              key={m.id}
              message={m}
              active={m.id === activeMessageId}
              blueprintOpen={showBlueprint && m.id === activeMessageId}
              highlighted={m.id === activeMessageId ? highlighted : null}
              onToggleBlueprint={() => onToggleBlueprint(m.id)}
              onHover={(index) => onHoverItem(m.id, index)}
              onSelect={(index) => onSelectItem(m.id, index)}
            />
          ),
        )}
      </div>

      <div className={cn("shrink-0 border-t border-border p-3", dropActive && "bg-safety/10")}>
        <div className="mb-2.5 flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              disabled={busy}
              onClick={() => submit(p)}
              className="rounded-sm border border-border bg-panel-raised px-2.5 py-1 font-mono text-[0.7rem] text-foreground transition-colors hover:border-safety hover:text-safety disabled:cursor-not-allowed disabled:opacity-40"
            >
              {p}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
          className="flex w-full items-center gap-2 rounded-sm border border-input bg-canvas p-1.5 focus-within:border-scan"
        >
          {!library && (
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={busy}
              aria-label="Read drawings"
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-sm border border-border px-2.5 font-mono text-[0.68rem] text-foreground transition-colors hover:border-safety hover:text-safety disabled:opacity-40"
            >
              <FileImage className="size-3.5" />
              Read drawings
            </button>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) onAddFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(input);
              }
            }}
            rows={horizontal ? 1 : 2}
            placeholder={files.length > 1 ? "Ask about these drawings…" : "Ask about this drawing…"}
            className="min-h-10 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="Send question"
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-sm bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-30"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </form>
      </div>
      </div>
    </div>
  );
}

function EmptyState({ dropActive }: { dropActive: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <BlueprintIntro />
      {dropActive && <p className="mt-4 text-sm text-safety">Drop the files to add them.</p>}
    </div>
  );
}

function BlueprintIntro({ large = false }: { large?: boolean }) {
  return (
    <div className="flex flex-col items-center text-center">
      <p className="font-display text-[0.975rem] tracking-[0.42em] text-muted-foreground">You ask</p>
      <h2 className={cn("mt-[0.975rem] font-display leading-none font-bold tracking-[0.18em] text-safety", large ? "text-[4.875rem]" : "text-[2.925rem]")}>
        Blueprints
      </h2>
      <p className="mt-[0.975rem] font-display text-[0.975rem] tracking-[0.42em] text-foreground">respond</p>
      <div className="mt-[1.95rem] h-px w-[6.5rem] bg-safety" aria-hidden />
      <p className={cn("mt-[1.95rem] leading-relaxed text-muted-foreground", large ? "max-w-md text-[1.3rem]" : "max-w-xs text-[1.1375rem]")}>
        We detect doors, windows, rooms, and columns on the sheet
      </p>
    </div>
  );
}

function AssistantMessage({
  message,
  active,
  blueprintOpen,
  highlighted,
  onToggleBlueprint,
  onHover,
  onSelect,
}: {
  message: Exclude<Extract<ChatMessage, { role: "assistant" }>, { status: "note" } | { status: "choose" }>;
  active: boolean;
  blueprintOpen: boolean;
  highlighted: number | null;
  onToggleBlueprint: () => void;
  onHover: (index: number | null) => void;
  onSelect: (index: number) => void;
}) {
  if (message.status === "pending") {
    return (
      <div className="rounded-sm border border-scan/40 bg-background/40 p-3">
        <FileReference name={message.fileName} />
        <div className="mt-2 flex items-center gap-2 font-mono text-xs text-scan">
          <Loader2 className="size-3.5 animate-spin" />
          ANALYZING SHEET<span className="animate-blink">_</span>
        </div>
      </div>
    );
  }
  if (message.status === "error") {
    return (
      <div className="rounded-sm border border-destructive/50 bg-destructive/10 p-3 text-sm text-foreground">
        <FileReference name={message.fileName} />
        <div className="mt-2 flex gap-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
          <span>{message.error}</span>
        </div>
      </div>
    );
  }

  const { result } = message;
  const hasItems = result.detections.length > 0;
  const speech = spokenAnswer(result);

  return (
    <div className={cn("rounded-sm border bg-background/40", active && hasItems ? "border-scan/60" : "border-border")}>
      <div className="p-3">
        <FileReference name={message.fileName} />
        <p className="mt-2 text-base leading-relaxed whitespace-pre-wrap text-foreground">{speech}</p>
      </div>

      <div className="border-t border-border px-3 py-2">
        <button
          type="button"
          onClick={onToggleBlueprint}
          aria-pressed={blueprintOpen}
          aria-expanded={blueprintOpen}
          className={cn(
            "inline-flex items-center gap-2 rounded-sm px-3 py-1.5 font-display text-sm font-semibold",
            blueprintOpen
              ? "border border-border text-foreground hover:border-safety hover:text-safety"
              : "bg-safety text-safety-foreground hover:opacity-90",
          )}
        >
          <Eye className="size-4" />
          Show blueprint
        </button>
      </div>

      {blueprintOpen && result.detections.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          <span className="label-tech">{kindSummary(result.detections)}</span>
        </div>
      )}

      {blueprintOpen && hasItems && (
        <div className="border-t border-border">
          <div className="px-3 py-2">
            <span className="label-tech">On this file</span>
          </div>
          <ul className="pb-1.5">
            {result.detections.map((d, i) => {
              const on = active && highlighted === i;
              const paint = markPaint(d.tag);
              const previous = result.detections[i - 1];
              const heading = !previous || detectionKind(previous.tag) !== detectionKind(d.tag);
              return (
                <li key={i}>
                  {heading && <div className="px-3 pt-2 pb-1 label-tech">{detectionKind(d.tag)}</div>}
                  <button
                    type="button"
                    onMouseEnter={() => onHover(i)}
                    onMouseLeave={() => onHover(null)}
                    onFocus={() => onHover(i)}
                    onBlur={() => onHover(null)}
                    onClick={() => onSelect(i)}
                    className={cn(
                      "flex w-full items-center gap-2.5 border-l-2 px-3 py-1.5 text-left transition-colors",
                      on ? "border-safety bg-safety/10" : "border-transparent hover:bg-accent/60",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-5 min-w-7 items-center justify-center rounded-[2px] px-1 font-mono text-[0.68rem] font-bold tabular-nums",
                        on ? "bg-safety text-safety-foreground" : paint.badge,
                      )}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.82rem] font-medium text-foreground">{d.tag}</span>
                      {d.label && <span className="block truncate text-xs text-muted-foreground">{d.label}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function FileReference({ name }: { name: string }) {
  return (
    <p className="flex min-w-0 items-center gap-1.5 font-mono text-sm text-scan">
      <FileImage className="size-3.5 shrink-0" />
      <span className="truncate">{name}</span>
    </p>
  );
}
