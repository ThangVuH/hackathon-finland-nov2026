/** Algorithmic project check. Compares quantities written in schedules and notes, then looks for a blueprint file whose name corresponds to the space. No model calls. */

export type CheckStatus = "match" | "mismatch" | "unchecked";

export interface ProjectDocument {
  name: string;
  /** A sheet the user can open: image or drawing PDF. */
  drawing: boolean;
  /** Spreadsheet rows. Each grid is one sheet. */
  grids?: { sheet: string; rows: string[][] }[];
  /** Prose from notes, specifications, or a PDF. */
  text?: string;
  /** Shown in the file list when the file could not be read. */
  note?: string;
}

export interface Quantity {
  source: string;
  quantity: number;
}

export interface Finding {
  space: string;
  element: string;
  status: CheckStatus;
  quantities: Quantity[];
  blueprint: string | null;
}

export interface CheckedFile {
  name: string;
  role: "Blueprint" | "Schedule" | "Notes" | "Unread";
  detail: string;
  /** Spreadsheet rows, when the file is a schedule. */
  rows?: string[][];
  /** Note or specification text. */
  text?: string;
}

export interface ProjectReport {
  headline: string;
  summary: string;
  fileCount: number;
  files: CheckedFile[];
  matches: number;
  mismatches: number;
  unchecked: number;
  findings: Finding[];
}

const ELEMENT_WORDS: Record<string, string> = {
  window: "window",
  windows: "window",
  door: "door",
  doors: "door",
  room: "room",
  rooms: "room",
  column: "column",
  columns: "column",
  stair: "stair",
  stairs: "stair",
  fixture: "fixture",
  fixtures: "fixture",
};

const SPACE_RE =
  /\b(?:meeting\s+room|bathroom|bedroom|office|kitchen|living|lobby|corridor|toilet|suite|level|bath|room|wc)\s*[-#]?\s*\d{0,3}\b|\b[A-Z]{1,3}-\d{2,4}\b/gi;

interface Claim {
  space: string;
  element: string;
  quantity: number;
  source: string;
}

export function checkProject(docs: ProjectDocument[]): ProjectReport {
  const claims: Claim[] = [];
  const drawings: string[] = [];
  const files: CheckedFile[] = [];

  for (const doc of docs) {
    if (doc.drawing) drawings.push(doc.name);
    const fromDoc: Claim[] = [];
    for (const grid of doc.grids ?? []) {
      const source = grid.sheet ? `${doc.name} · ${grid.sheet}` : doc.name;
      fromDoc.push(...claimsFromGrid(grid.rows, source));
    }
    if (doc.text?.trim()) fromDoc.push(...claimsFromText(doc.text, doc.name));

    const unique = dedupeClaims(fromDoc);
    claims.push(...unique);

    const rows = previewRows(doc);
    const text = doc.text?.trim();
    files.push({
      name: doc.name,
      role: fileRole(doc, unique.length),
      detail: fileDetail(doc, unique.length),
      ...(rows ? { rows } : {}),
      ...(text ? { text } : {}),
    });
  }

  const groups = new Map<string, Claim[]>();
  for (const claim of claims) {
    const key = `${norm(claim.space)}|${claim.element}`;
    const list = groups.get(key) ?? [];
    list.push(claim);
    groups.set(key, list);
  }

  const findings: Finding[] = [];
  for (const group of groups.values()) {
    const quantities = mergeQuantities(group);
    const space = displaySpace(group.map((c) => c.space));
    const element = group[0]!.element;
    const blueprint = bestDrawing(space, drawings);
    const distinct = new Set(quantities.map((q) => q.quantity));
    const status: CheckStatus = distinct.size > 1 ? "mismatch" : blueprint ? "match" : "unchecked";
    findings.push({ space, element, status, quantities, blueprint });
  }

  findings.sort((a, b) => statusRank(a.status) - statusRank(b.status) || a.space.localeCompare(b.space) || a.element.localeCompare(b.element));

  const matches = findings.filter((f) => f.status === "match").length;
  const mismatches = findings.filter((f) => f.status === "mismatch").length;
  const unchecked = findings.filter((f) => f.status === "unchecked").length;
  const { headline, summary } = narrate(docs.length, findings);

  return { headline, summary, fileCount: docs.length, files, matches, mismatches, unchecked, findings };
}

export function claimsFromText(text: string, source: string): Claim[] {
  const claims: Claim[] = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const spaces = [...line.matchAll(SPACE_RE)].map((m) => ({
      space: cleanSpace(m[0]),
      index: m.index ?? 0,
      length: m[0].length,
    }));
    if (!spaces.length) continue;
    for (const hit of quantityHits(line)) {
      const insideSpace = spaces.some((space) => hit.index >= space.index && hit.index < space.index + space.length);
      if (insideSpace) continue;
      const before = spaces.filter((s) => s.index <= hit.index);
      const space = (before.length ? before[before.length - 1] : spaces[0])!.space;
      claims.push({ space, element: hit.element, quantity: hit.quantity, source });
    }
  }
  return claims;
}

export function claimsFromGrid(rows: string[][], source: string): Claim[] {
  const grid = rows.map((row) => row.map((cell) => cell.trim())).filter((row) => row.some(Boolean));
  if (!grid.length) return [];

  let headerIdx = -1;
  let elementHeaders = 0;
  for (let r = 0; r < Math.min(grid.length, 8); r++) {
    const count = grid[r]!.filter((cell) => elementOf(cell)).length;
    if (count > elementHeaders) {
      elementHeaders = count;
      headerIdx = r;
    }
  }

  const claims: Claim[] = [];
  if (headerIdx >= 0 && elementHeaders > 0) {
    const header = grid[headerIdx]!;
    const elementCols = header
      .map((cell, index) => ({ index, element: elementOf(cell) }))
      .filter((col): col is { index: number; element: string } => Boolean(col.element));
    const spaceCol = Math.max(0, header.findIndex((_, index) => !elementCols.some((col) => col.index === index)));
    for (const row of grid.slice(headerIdx + 1)) {
      const space = cleanSpace(row[spaceCol] ?? "");
      if (!space || /^\d+$/.test(space)) continue;
      for (const col of elementCols) {
        const quantity = parseQty(row[col.index] ?? "");
        if (quantity == null) continue;
        claims.push({ space, element: col.element, quantity, source });
      }
    }
  }

  const tall = tallClaims(grid, source);
  const blob = grid.map((row) => row.join(" | ")).join("\n");
  return dedupeClaims([...claims, ...tall, ...claimsFromText(blob, source)]);
}

function tallClaims(grid: string[][], source: string): Claim[] {
  let headerIdx = -1;
  for (let r = 0; r < Math.min(grid.length, 8); r++) {
    const row = grid[r]!;
    const hasSpace = row.some(isSpaceHeader);
    const hasElement = row.some(isElementHeader);
    const hasQty = row.some(isQtyHeader);
    if (hasSpace && hasElement && hasQty) {
      headerIdx = r;
      break;
    }
  }
  if (headerIdx < 0) return [];
  const header = grid[headerIdx]!;
  const spaceCol = header.findIndex(isSpaceHeader);
  const elementCol = header.findIndex(isElementHeader);
  const qtyCol = header.findIndex(isQtyHeader);
  const claims: Claim[] = [];
  for (const row of grid.slice(headerIdx + 1)) {
    const space = cleanSpace(row[spaceCol] ?? "");
    const element = elementOf(row[elementCol] ?? "");
    const quantity = parseQty(row[qtyCol] ?? "");
    if (!space || !element || quantity == null) continue;
    claims.push({ space, element, quantity, source });
  }
  return claims;
}

function quantityHits(line: string): { element: string; quantity: number; index: number }[] {
  const hits: { element: string; quantity: number; index: number }[] = [];
  const numberFirst = /(\d{1,4})\s+(windows?|doors?|rooms?|columns?|stairs?|fixtures?)\b/gi;
  const wordFirst = /\b(windows?|doors?|rooms?|columns?|stairs?|fixtures?)\b\s*[:\-–]?\s*(\d{1,4})\b/gi;
  const changedTo = /\b(windows?|doors?|rooms?|columns?|stairs?|fixtures?)\b[^\n.]{0,40}?\b(?:to|at)\s+(\d{1,4})\b/gi;
  for (const match of line.matchAll(numberFirst)) {
    const element = elementOf(match[2] ?? "");
    const quantity = Number(match[1]);
    if (element && Number.isInteger(quantity)) hits.push({ element, quantity, index: match.index ?? 0 });
  }
  for (const match of line.matchAll(wordFirst)) addHit(match[1], match[2], match.index);
  for (const match of line.matchAll(changedTo)) addHit(match[1], match[2], match.index);
  return hits;

  function addHit(word: string | undefined, raw: string | undefined, index: number | undefined) {
    const element = elementOf(word ?? "");
    const quantity = Number(raw);
    const at = index ?? 0;
    if (!element || !Number.isInteger(quantity)) return;
    const already = hits.some((hit) => hit.element === element && hit.quantity === quantity && Math.abs(hit.index - at) < 24);
    if (!already) hits.push({ element, quantity, index: at });
  }
}

function mergeQuantities(claims: Claim[]): Quantity[] {
  const bySource = new Map<string, number>();
  for (const claim of claims) {
    const previous = bySource.get(claim.source);
    if (previous == null || previous === claim.quantity) bySource.set(claim.source, claim.quantity);
  }
  return [...bySource.entries()].map(([source, quantity]) => ({ source, quantity }));
}

function dedupeClaims(claims: Claim[]): Claim[] {
  const seen = new Set<string>();
  const out: Claim[] = [];
  for (const claim of claims) {
    const key = `${norm(claim.space)}|${claim.element}|${claim.quantity}|${claim.source}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(claim);
  }
  return out;
}

export function drawingMatchesSpace(space: string, drawingName: string): boolean {
  const wanted = norm(space);
  const drawing = norm(stripExt(drawingName));
  if (!wanted || !drawing) return false;
  if (drawing.includes(wanted)) return true;
  const tokens = wanted.split(" ").filter((token) => token.length > 1 || /\d/.test(token));
  if (!tokens.length) return false;
  const have = new Set(drawing.split(" "));
  return tokens.every((token) => have.has(token));
}

function bestDrawing(space: string, drawings: string[]): string | null {
  const wanted = norm(space);
  const hits = drawings.filter((name) => drawingMatchesSpace(space, name));
  hits.sort((a, b) => {
    const aFull = norm(stripExt(a)).includes(wanted) ? 0 : 1;
    const bFull = norm(stripExt(b)).includes(wanted) ? 0 : 1;
    if (aFull !== bFull) return aFull - bFull;
    return a.length - b.length;
  });
  return hits[0] ?? null;
}

function narrate(fileCount: number, findings: Finding[]): { headline: string; summary: string } {
  if (!fileCount) {
    return {
      headline: "No project uploaded",
      summary: "Upload the drawings, schedules, specifications, and notes. The check runs as soon as the files are in.",
    };
  }
  if (!findings.length) {
    return {
      headline: "No quantities to compare",
      summary: `${fileCount} ${pluralFiles(fileCount)} checked. No window, door, or similar counts were found. A schedule needs a space name and a number, such as Office 1 and its windows.`,
    };
  }

  const mismatches = findings.filter((f) => f.status === "mismatch");
  const unchecked = findings.filter((f) => f.status === "unchecked");
  const matches = findings.filter((f) => f.status === "match");
  const headline = mismatches.length
    ? "Conflicts in the project set"
    : unchecked.length
      ? "Blueprints missing for some claims"
      : "Project files agree";

  const sentences = [`${fileCount} ${pluralFiles(fileCount)} checked.`, agreeSentence(matches.length)];
  if (mismatches.length) {
    const detail = mismatches
      .slice(0, 3)
      .map((finding) => {
        const bits = finding.quantities.map((q) => `${q.quantity} in ${q.source}`).join(" and ");
        return `${finding.space} ${pluralElement(finding.element)} ${finding.quantities.length > 1 ? "are" : "is"} ${bits}`;
      })
      .join(". ");
    sentences.push(`${mismatches.length} ${mismatches.length === 1 ? "conflict" : "conflicts"}. ${detail}.`);
  }
  if (unchecked.length) {
    const names = unchecked
      .slice(0, 3)
      .map((finding) => `${finding.space} ${pluralElement(finding.element)}`)
      .join(", ");
    sentences.push(
      `${unchecked.length} ${unchecked.length === 1 ? "claim has" : "claims have"} no corresponding blueprint: ${names}.`,
    );
  }
  return { headline, summary: sentences.join(" ") };
}

function previewRows(doc: ProjectDocument): string[][] | undefined {
  const grids = (doc.grids ?? []).filter((grid) => grid.rows.some((row) => row.some(Boolean)));
  if (!grids.length) return undefined;
  if (grids.length === 1) return grids[0]!.rows;
  const rows: string[][] = [];
  for (const grid of grids) {
    if (grid.sheet) rows.push([grid.sheet]);
    rows.push(...grid.rows);
  }
  return rows;
}

function fileRole(doc: ProjectDocument, claims: number): CheckedFile["role"] {
  if (doc.note && !doc.drawing && claims === 0) return "Unread";
  if (doc.grids?.some((grid) => grid.rows.length)) return "Schedule";
  if (doc.drawing) return "Blueprint";
  if (doc.text?.trim() || claims > 0) return "Notes";
  return "Unread";
}

function fileDetail(doc: ProjectDocument, claims: number): string {
  if (doc.note && claims === 0 && !doc.drawing) return doc.note;
  if (claims > 0 && doc.drawing) return `${claims} ${claims === 1 ? "quantity" : "quantities"} · blueprint`;
  if (doc.drawing) return "Blueprint";
  if (claims > 0) return `${claims} ${claims === 1 ? "quantity" : "quantities"}`;
  if (doc.note) return doc.note;
  return "No quantities found";
}

function elementOf(value: string): string | null {
  const word = value.trim().toLowerCase().replace(/[^a-z]/g, "");
  return ELEMENT_WORDS[word] ?? null;
}

function parseQty(value: string): number | null {
  const cleaned = value.trim().replace(/,/g, "");
  if (!/^\d{1,4}(?:\.0+)?$/.test(cleaned)) return null;
  const quantity = Math.round(Number(cleaned));
  return Number.isInteger(quantity) ? quantity : null;
}

function cleanSpace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function displaySpace(values: string[]): string {
  const cleaned = values.map(cleanSpace).filter(Boolean);
  cleaned.sort((a, b) => b.length - a.length);
  return cleaned[0] ?? "Space";
}

function norm(value: string): string {
  return value
    .toLowerCase()
    .replace(/\.[a-z0-9]{1,5}$/i, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stripExt(name: string): string {
  return name.replace(/\.[a-z0-9]{1,5}$/i, "");
}

function statusRank(status: CheckStatus): number {
  if (status === "mismatch") return 0;
  if (status === "unchecked") return 1;
  return 2;
}

function pluralFiles(count: number): string {
  return count === 1 ? "file" : "files";
}

function agreeSentence(count: number): string {
  if (count === 1) return "1 claim agrees and has a matching blueprint.";
  return `${count} claims agree and have a matching blueprint.`;
}

function pluralElement(element: string): string {
  if (element === "stair") return "stairs";
  if (element === "fixture") return "fixtures";
  return `${element}s`;
}

function isSpaceHeader(cell: string): boolean {
  return /^(space|room|name|area|zone|location|sheet)$/i.test(cell.trim());
}

function isElementHeader(cell: string): boolean {
  return /^(element|item|type|component|opening)$/i.test(cell.trim());
}

function isQtyHeader(cell: string): boolean {
  return /^(qty|quantity|count|number|nr|no\.?|#)$/i.test(cell.trim());
}
