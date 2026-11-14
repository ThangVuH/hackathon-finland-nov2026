import { useState } from "react";
import { FileWarning, FolderCheck, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { CheckedFile, CheckStatus, Finding, ProjectReport } from "@/lib/project-check";

interface Props {
  report: ProjectReport | null;
  checking: boolean;
  onOpenBlueprint: (filename: string) => void;
  onLoadSample: () => void;
}

export function ProjectCheckPanel({ report, checking, onOpenBlueprint, onLoadSample }: Props) {
  const [openFile, setOpenFile] = useState<string | null>(null);
  return (
    <div className="flex h-full min-h-0 flex-col bg-panel">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
        <FolderCheck className="size-4 text-safety" />
        <span className="font-display text-sm font-semibold text-foreground">Project Check</span>
        <button
          type="button"
          onClick={onLoadSample}
          disabled={checking}
          className="ml-auto font-mono text-[0.68rem] tracking-wide text-scan uppercase underline-offset-2 hover:underline disabled:opacity-50"
        >
          Load sample
        </button>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {checking && (
          <div className="rounded-sm border border-border bg-background/40 p-3">
            <div className="flex items-center gap-2 font-mono text-xs text-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              CHECKING FILES
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">Comparing schedules, notes, and blueprint names on this computer.</p>
          </div>
        )}

        {!checking && !report && <EmptyState onLoadSample={onLoadSample} />}

        {report && (
          <>
            <section className="rounded-sm border border-border bg-background/40 p-3">
              <p className="label-tech">Executive summary</p>
              <h2 className="mt-2 font-display text-2xl leading-none font-bold text-safety">{report.headline}</h2>
              <p className="mt-3 text-sm leading-relaxed text-foreground">{report.summary}</p>
              <dl className="mt-4 grid grid-cols-3 gap-2">
                <Stat label="Match" value={report.matches} tone="match" />
                <Stat label="Conflict" value={report.mismatches} tone="mismatch" />
                <Stat label="No sheet" value={report.unchecked} tone="unchecked" />
              </dl>
            </section>

            {report.findings.length > 0 && (
              <section>
                <p className="label-tech mb-2">Claims</p>
                <ul className="space-y-1.5">
                  {report.findings.map((finding) => (
                    <FindingRow key={`${finding.space}-${finding.element}`} finding={finding} onOpenBlueprint={onOpenBlueprint} />
                  ))}
                </ul>
              </section>
            )}

            <section>
              <p className="label-tech mb-2">Files</p>
              <ul className="space-y-1">
                {report.files.map((file) => (
                  <FileRow
                    key={file.name}
                    file={file}
                    open={openFile === file.name}
                    onToggle={() => {
                      setOpenFile((current) => (current === file.name ? null : file.name));
                      if (file.role === "Blueprint") onOpenBlueprint(file.name);
                    }}
                  />
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function FileRow({ file, open, onToggle }: { file: CheckedFile; open: boolean; onToggle: () => void }) {
  return (
    <li className="border-b border-border/70 py-1.5">
      <button type="button" onClick={onToggle} className="flex w-full items-baseline justify-between gap-3 text-left">
        <span className="min-w-0 truncate text-sm text-foreground underline-offset-2 hover:underline">{file.name}</span>
        <span className="shrink-0 font-mono text-[0.62rem] tracking-wide text-muted-foreground uppercase">
          {file.role} · {open ? "Hide" : "Open"}
        </span>
      </button>
      {open && <FileBody file={file} />}
    </li>
  );
}

function FileBody({ file }: { file: CheckedFile }) {
  if (file.rows?.length) {
    return (
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <tbody>
            {file.rows.map((row, index) => (
              <tr key={index} className={index === 0 ? "text-muted-foreground" : "text-foreground"}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border border-border px-2 py-1">
                    {cell || "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (file.text) {
    return <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap text-foreground">{file.text}</p>;
  }
  return <p className="mt-2 text-xs text-muted-foreground">Opened on the sheet.</p>;
}

function FindingRow({ finding, onOpenBlueprint }: { finding: Finding; onOpenBlueprint: (filename: string) => void }) {
  const tone = toneClass(finding.status);
  return (
    <li className="rounded-sm border border-border bg-background/40 px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          {finding.space} · {elementLabel(finding.element)}
        </span>
        <span className={cn("font-mono text-[0.62rem] tracking-wide uppercase", tone)}>{label(finding.status)}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {finding.quantities.map((q) => `${q.quantity} in ${q.source}`).join(" · ")}
      </p>
      {finding.blueprint ? (
        <button
          type="button"
          onClick={() => onOpenBlueprint(finding.blueprint!)}
          className="mt-1.5 font-mono text-[0.68rem] text-scan underline-offset-2 hover:underline"
        >
          SHEET {finding.blueprint}
        </button>
      ) : (
        <p className="mt-1.5 flex items-center gap-1.5 font-mono text-[0.68rem] text-muted-foreground">
          <FileWarning className="size-3" />
          NO CORRESPONDING BLUEPRINT
        </p>
      )}
    </li>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: CheckStatus }) {
  return (
    <div className="rounded-sm border border-border px-2 py-1.5">
      <dt className="label-tech">{label}</dt>
      <dd className={cn("font-mono text-xl font-bold tabular-nums", toneClass(tone))}>{value}</dd>
    </div>
  );
}

function EmptyState({ onLoadSample }: { onLoadSample: () => void }) {
  return (
    <div>
      <h2 className="font-display text-2xl leading-[0.95] font-bold text-foreground">
        Drop the project.
        <br />
        <span className="text-safety">The check runs itself.</span>
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
        Add drawings together with the Excel schedule, specifications, and meeting notes. Counts are compared on this computer, and each space is paired with a blueprint by its name.
      </p>
      <button
        type="button"
        onClick={onLoadSample}
        className="mt-4 rounded-sm border border-safety bg-safety/10 px-3 py-1.5 font-display text-sm font-semibold text-foreground hover:bg-safety/20"
      >
        Load sample project
      </button>
    </div>
  );
}

function elementLabel(element: string): string {
  if (element === "stair") return "stairs";
  if (element === "fixture") return "fixtures";
  return `${element}s`;
}

function label(status: CheckStatus): string {
  if (status === "match") return "Match";
  if (status === "mismatch") return "Conflict";
  return "No sheet";
}

function toneClass(status: CheckStatus): string {
  if (status === "match") return "text-scan";
  if (status === "mismatch") return "text-safety";
  return "text-muted-foreground";
}
