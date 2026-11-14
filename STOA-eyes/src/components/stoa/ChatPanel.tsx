import { useEffect, useRef, useState } from "react";
import { ArrowUp, Eye, EyeOff, Loader2, ScanSearch, TriangleAlert } from "lucide-react";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { AnalysisResult, Verdict } from "@/lib/detections";

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; status: "pending" }
  | { id: string; role: "assistant"; status: "error"; error: string }
  | { id: string; role: "assistant"; status: "done"; result: AnalysisResult };

const QUICK_PROMPTS = ["How many doors?", "Count all windows", "How many rooms?", "Count the columns"];

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  activeMessageId: string | null;
  highlighted: number | null;
  showBoxes: boolean;
  backendNote: string;
  onShowBoxesChange: (v: boolean) => void;
  onAsk: (question: string) => void;
  onActivate: (messageId: string) => void;
  onHover: (messageId: string, index: number | null) => void;
  onSelect: (messageId: string, index: number) => void;
}

export function ChatPanel({
  messages,
  busy,
  activeMessageId,
  highlighted,
  showBoxes,
  backendNote,
  onShowBoxesChange,
  onAsk,
  onActivate,
  onHover,
  onSelect,
}: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

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
    <div className="flex h-full min-h-0 flex-col bg-panel">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex min-w-0 items-center gap-2">
          <ScanSearch className="size-4 shrink-0 text-safety" />
          <span className="font-display text-sm font-semibold text-foreground">Drawing Q&amp;A</span>
          <span className="label-tech truncate">{backendNote}</span>
        </div>
        <label className="flex cursor-pointer items-center gap-2">
          {showBoxes ? <Eye className="size-3.5 text-scan" /> : <EyeOff className="size-3.5 text-muted-foreground" />}
          <span className="label-tech">{showBoxes ? "Boxes on" : "Boxes off"}</span>
          <Switch
            checked={showBoxes}
            onCheckedChange={onShowBoxesChange}
            aria-label="Show or hide bounding boxes"
            className="data-[state=checked]:bg-scan"
          />
        </label>
      </div>

      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && <EmptyState />}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-sm border border-border bg-panel-raised px-3 py-2 text-sm text-foreground">
                {m.text}
              </div>
            </div>
          ) : (
            <AssistantMessage
              key={m.id}
              message={m}
              active={m.id === activeMessageId}
              highlighted={m.id === activeMessageId ? highlighted : null}
              showBoxes={showBoxes}
              onActivate={() => onActivate(m.id)}
              onHover={(i) => onHover(m.id, i)}
              onSelect={(i) => onSelect(m.id, i)}
            />
          ),
        )}
      </div>

      <div className="shrink-0 border-t border-border p-3">
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
          className="flex items-end gap-2 rounded-sm border border-input bg-background p-1.5 focus-within:border-scan"
        >
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
            placeholder="Ask about this drawing…"
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

function EmptyState() {
  return (
    <div className="flex h-full flex-col justify-center gap-3 py-8">
      <div className="hazard-stripe h-1.5 w-16" />
      <h2 className="font-display text-2xl leading-tight font-bold text-foreground">
        Ask the drawing.
        <br />
        <span className="text-safety">Verify every count.</span>
      </h2>
      <p className="text-sm leading-relaxed text-muted-foreground">
        Window and door counts are compared with a second model. When the two disagree, click a highlighted box to keep it or drop it.
      </p>
    </div>
  );
}

const VERDICT_LABEL: Record<Verdict, string> = {
  reliable: "RELIABLE",
  review: "CHECK",
  unverified: "NOT CHECKED",
  refused: "OUT OF SCOPE",
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <p
      className={cn(
        "mb-2 font-mono text-[0.68rem] tracking-[0.14em]",
        verdict === "reliable" && "text-scan",
        verdict === "review" && "text-safety",
        verdict === "unverified" && "text-muted-foreground",
        verdict === "refused" && "text-destructive",
      )}
    >
      {VERDICT_LABEL[verdict]}
    </p>
  );
}

function AssistantMessage({
  message,
  active,
  highlighted,
  showBoxes,
  onActivate,
  onHover,
  onSelect,
}: {
  message: Extract<ChatMessage, { role: "assistant" }>;
  active: boolean;
  highlighted: number | null;
  showBoxes: boolean;
  onActivate: () => void;
  onHover: (i: number | null) => void;
  onSelect: (i: number) => void;
}) {
  if (message.status === "pending") {
    return (
      <div className="rounded-sm border border-scan/40 bg-background/40 p-3">
        <div className="flex items-center gap-2 font-mono text-xs text-scan">
          <Loader2 className="size-3.5 animate-spin" />
          ANALYZING SHEET<span className="animate-blink">_</span>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">Scanning the drawing and locating each element…</p>
      </div>
    );
  }
  if (message.status === "error") {
    return (
      <div className="flex gap-2 rounded-sm border border-destructive/50 bg-destructive/10 p-3 text-sm text-foreground">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
        <span>{message.error}</span>
      </div>
    );
  }

  const { result } = message;
  const hasItems = result.detections.length > 0;

  return (
    <div
      className={cn(
        "rounded-sm border bg-background/40 transition-colors",
        active && hasItems ? "border-scan/60" : "border-border",
      )}
    >
      <div className="p-3">
        {result.verdict && <VerdictBadge verdict={result.verdict} />}
        {hasItems && (
          <div className="mb-2 flex items-baseline gap-2">
            <span className="font-mono text-3xl leading-none font-bold text-safety tabular-nums">{result.count}</span>
            <span className="label-tech">
              {result.objectType}
              {result.count === 1 ? "" : "s"} detected
            </span>
          </div>
        )}
        <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">{result.answer}</p>
        {result.warning && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{result.warning}</p>}
      </div>

      {hasItems && (
        <div className="border-t border-border">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="label-tech">Verification list</span>
            {!active ? (
              <button
                type="button"
                onClick={onActivate}
                className="font-mono text-[0.7rem] text-scan underline-offset-2 hover:underline"
              >
                SHOW ON DRAWING
              </button>
            ) : (
              <span className="font-mono text-[0.65rem] text-muted-foreground">[ymin, xmin, ymax, xmax]</span>
            )}
          </div>
          <ul className={cn("pb-1.5", (!active || !showBoxes) && "opacity-60")}>
            {result.detections.map((d, i) => {
              const on = active && highlighted === i;
              const dropped = d.included === false;
              return (
                <li key={i}>
                  <button
                    type="button"
                    onMouseEnter={() => active && onHover(i)}
                    onMouseLeave={() => active && onHover(null)}
                    onFocus={() => active && onHover(i)}
                    onBlur={() => active && onHover(null)}
                    onClick={() => onSelect(i)}
                    className={cn(
                      "flex w-full items-center gap-2.5 border-l-2 px-3 py-1.5 text-left transition-colors",
                      dropped && "opacity-50",
                      on ? "border-safety bg-safety/10" : d.disputed ? "border-safety/70 hover:bg-safety/10" : "border-transparent hover:bg-accent/60",
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
                      <span className={cn("block truncate text-[0.82rem] font-medium text-foreground", dropped && "line-through")}>
                        {d.tag}
                        {d.disputed ? (dropped ? " · dropped" : " · check") : ""}
                      </span>
                      {d.label && <span className="block truncate text-xs text-muted-foreground">{d.label}</span>}
                    </span>
                    <span className="shrink-0 font-mono text-[0.62rem] text-muted-foreground tabular-nums">
                      [{d.box.join(", ")}]
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
