import { useEffect, useRef, useState } from "react";
import { ArrowUp, FileImage, Loader2, ScanSearch, TriangleAlert, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/detections";

export type ChatFile = { id: string; name: string };

export type ChatMessage =
  | { id: string; role: "user"; text: string; files: ChatFile[] }
  | { id: string; role: "assistant"; status: "pending"; fileId: string; fileName: string }
  | { id: string; role: "assistant"; status: "error"; error: string; fileId: string; fileName: string }
  | { id: string; role: "assistant"; status: "done"; result: AnalysisResult; fileId: string; fileName: string };

const QUICK_PROMPTS = ["How many doors?", "Count all windows", "How many rooms?", "Count the columns"];

interface Props {
  messages: ChatMessage[];
  files: ChatFile[];
  busy: boolean;
  backendNote: string;
  activeFileId: string | null;
  activeMessageId: string | null;
  highlighted: number | null;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveFile: (id: string) => void;
  onOpenFile: (id: string) => void;
  onAsk: (question: string) => void;
  onHoverItem: (messageId: string, index: number | null) => void;
  onSelectItem: (messageId: string, index: number) => void;
}

export function ChatPanel({
  messages,
  files,
  busy,
  backendNote,
  activeFileId,
  activeMessageId,
  highlighted,
  onAddFiles,
  onRemoveFile,
  onOpenFile,
  onAsk,
  onHoverItem,
  onSelectItem,
}: Props) {
  const [input, setInput] = useState("");
  const [dropActive, setDropActive] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

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

  return (
    <div
      className="flex h-full min-h-0 flex-col bg-panel"
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
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
        <ScanSearch className="size-4 shrink-0 text-safety" />
        <span className="font-display text-sm font-semibold text-foreground">Drawing Q&amp;A</span>
        <span className="label-tech truncate">{backendNote}</span>
      </div>

      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && <EmptyState dropActive={dropActive} />}
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
          ) : (
            <AssistantMessage
              key={m.id}
              message={m}
              active={m.id === activeMessageId}
              highlighted={m.id === activeMessageId ? highlighted : null}
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
        {files.length > 0 && (
          <ul className="mb-2.5 flex flex-wrap gap-1.5" aria-label="Drawings to read">
            {files.map((file) => (
              <li key={file.id} className={cn("flex max-w-full items-center gap-1 rounded-sm border bg-panel-raised py-1 pr-1 pl-2", file.id === activeFileId ? "border-safety" : "border-border")}>
                <button type="button" onClick={() => onOpenFile(file.id)} className="flex min-w-0 items-center gap-1">
                  <FileImage className="size-3.5 shrink-0 text-scan" />
                  <span className="truncate font-mono text-[0.7rem] text-foreground">{file.name}</span>
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  disabled={busy}
                  onClick={() => onRemoveFile(file.id)}
                  className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
          className="flex items-end gap-2 rounded-sm border border-input bg-background p-1.5 focus-within:border-scan"
        >
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
          <input
            id="drawing-files"
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
            rows={2}
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
  );
}

function EmptyState({ dropActive }: { dropActive: boolean }) {
  return (
    <div className="flex h-full flex-col justify-center gap-3 py-8">
      <div className="hazard-stripe h-1.5 w-16" />
      <h2 className="font-display text-2xl leading-tight font-bold text-foreground">
        Ask the drawings.
        <br />
        <span className="text-safety">Read the count.</span>
      </h2>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
        Add one or more drawings. Each answer gives the count and the file it came from.
        {dropActive ? " Drop the files to add them." : ""}
      </p>
    </div>
  );
}

function AssistantMessage({
  message,
  active,
  highlighted,
  onHover,
  onSelect,
}: {
  message: Extract<ChatMessage, { role: "assistant" }>;
  active: boolean;
  highlighted: number | null;
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
  const direct = /^(yes|no)\b/i.test(result.answer.trim());

  return (
    <div className={cn("rounded-sm border bg-background/40", active && hasItems ? "border-scan/60" : "border-border")}>
      <div className="p-3">
        <FileReference name={message.fileName} />
        {hasItems && !direct && (
          <div className="mt-2 mb-2 flex items-baseline gap-2">
            <span className="font-mono text-3xl leading-none font-bold text-safety tabular-nums">{result.count}</span>
            <span className="label-tech">
              {result.objectType}
              {result.count === 1 ? "" : "s"} detected
            </span>
          </div>
        )}
        <p className={cn("leading-relaxed whitespace-pre-wrap text-foreground", direct ? "mt-2 text-base font-medium" : "text-sm", hasItems && !direct ? "" : "mt-2")}>
          {result.answer}
        </p>
      </div>

      {hasItems && (
        <div className="border-t border-border">
          <div className="px-3 py-2">
            <span className="label-tech">On this file</span>
          </div>
          <ul className="pb-1.5">
            {result.detections.map((d, i) => {
              const on = active && highlighted === i;
              return (
                <li key={i}>
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
                        on ? "bg-safety text-safety-foreground" : "bg-scan text-scan-foreground",
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
    <p className="flex min-w-0 items-center gap-1.5 font-mono text-[0.68rem] text-scan">
      <FileImage className="size-3.5 shrink-0" />
      <span className="truncate">{name}</span>
    </p>
  );
}
