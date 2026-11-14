/** Shared types + normalization for AI detections. Coordinates use [ymin, xmin, ymax, xmax] on a 0-1000 scale. */

export type Box = [ymin: number, xmin: number, ymax: number, xmax: number];

export interface Detection {
  /** Display tag, e.g. "Door #1". */
  tag: string;
  /** Model's short descriptor, e.g. "Entry door" or "Bedroom 1". */
  label: string;
  box: Box;
}

export interface AnalysisResult {
  answer: string;
  objectType: string;
  count: number;
  detections: Detection[];
}

export interface RawAnalysis {
  answer: string;
  object_type: string;
  count: number;
  items: { label: string; kind?: string; ymin: number; xmin: number; ymax: number; xmax: number }[];
}

const KINDS = ["door", "window", "room", "column", "stair"] as const;

/** The object family named by a tag such as "Window #2". */
export function detectionKind(tag: string): string {
  return tagType(tag) || "object";
}

export function kindSummary(detections: Detection[]): string {
  const counts = new Map<string, number>();
  for (const item of detections) {
    const kind = titleCase(detectionKind(item.tag));
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts].map(([kind, count]) => `${count} ${kind}${count === 1 ? "" : "s"}`).join(" · ");
}

const clamp = (n: number) => Math.min(1000, Math.max(0, Math.round(Number.isFinite(n) ? n : 0)));

function titleCase(s: string) {
  const t = s.trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "Item";
}

/** Clamps to 0-1000, fixes inverted corners, drops zero-area boxes and numbers each kind on its own. */
export function normalizeAnalysis(raw: RawAnalysis): AnalysisResult {
  const detections: Detection[] = [];
  const seen = new Map<string, number>();
  for (const item of raw.items ?? []) {
    let ymin = clamp(item.ymin);
    let xmin = clamp(item.xmin);
    let ymax = clamp(item.ymax);
    let xmax = clamp(item.xmax);
    if (ymin > ymax) [ymin, ymax] = [ymax, ymin];
    if (xmin > xmax) [xmin, xmax] = [xmax, xmin];
    if (ymax - ymin < 1 || xmax - xmin < 1) continue;
    const kind = itemKind(item.kind, item.label, raw.object_type);
    const next = (seen.get(kind) ?? 0) + 1;
    seen.set(kind, next);
    detections.push({
      tag: `${titleCase(kind)} #${next}`,
      label: (item.label || "").trim(),
      box: [ymin, xmin, ymax, xmax],
    });
  }
  const kinds = [...seen.keys()];
  const objectType = kinds.length === 1 ? titleCase(kinds[0]!) : "Object";
  const count = detections.length > 0 ? detections.length : Math.max(0, Math.round(raw.count || 0));
  return { answer: raw.answer.trim(), objectType, count, detections };
}

function itemKind(kind: string | undefined, label: string, objectType: string): string {
  return namedKind(kind) || namedKind(label) || namedKind(objectType) || "object";
}

function namedKind(value: string | undefined): string | null {
  const text = (value ?? "").toLowerCase();
  for (const kind of KINDS) {
    if (new RegExp(`\\b${kind}s?\\b`).test(text)) return kind;
  }
  return null;
}

/** Keep the number and name an item received the first time it was found on this sheet. Each kind keeps its own numbers. */
export function stabilizeDetections(known: Detection[], result: AnalysisResult): AnalysisResult {
  const detections = result.detections.map((item) => ({ ...item }));
  const kinds = [...new Set(detections.map((item) => detectionKind(item.tag)))];
  for (const kind of kinds) {
    const indexes = detections.flatMap((item, index) => (detectionKind(item.tag) === kind ? [index] : []));
    const prior = known.filter((item) => detectionKind(item.tag) === kind);
    const used = new Set<number>();
    const pairs: { index: number; priorIndex: number; score: number }[] = [];
    for (const index of indexes) {
      const item = detections[index]!;
      prior.forEach((earlier, priorIndex) => {
        const overlap = iou(item.box, earlier.box);
        const sameName = labelsMatch(item.label, earlier.label);
        const close = centerDistance(item.box, earlier.box) <= 80;
        if (overlap < 0.2 && !(sameName && (close || overlap >= 0.05))) return;
        pairs.push({ index, priorIndex, score: overlap + (sameName ? 0.5 : 0) });
      });
    }
    pairs.sort((a, b) => b.score - a.score);
    const takenNew = new Set<number>();
    const takenPrior = new Set<number>();
    const matched = new Map<number, Detection>();
    for (const pair of pairs) {
      if (takenNew.has(pair.index) || takenPrior.has(pair.priorIndex)) continue;
      const earlier = prior[pair.priorIndex]!;
      const item = detections[pair.index]!;
      takenNew.add(pair.index);
      takenPrior.add(pair.priorIndex);
      used.add(tagNumber(earlier.tag));
      matched.set(pair.index, { tag: earlier.tag, label: earlier.label || item.label, box: item.box });
    }
    let next = prior.reduce((max, item) => Math.max(max, tagNumber(item.tag)), 0);
    for (const index of indexes) {
      const kept = matched.get(index);
      if (kept) {
        detections[index] = kept;
        continue;
      }
      next += 1;
      while (used.has(next)) next += 1;
      used.add(next);
      detections[index] = { ...detections[index]!, tag: `${titleCase(kind)} #${next}` };
    }
  }
  detections.sort((a, b) => kindRank(detectionKind(a.tag)) - kindRank(detectionKind(b.tag)) || tagNumber(a.tag) - tagNumber(b.tag));
  return { ...result, detections };
}

function kindRank(kind: string): number {
  const rank = KINDS.indexOf(kind as (typeof KINDS)[number]);
  return rank === -1 ? KINDS.length : rank;
}

function tagNumber(tag: string): number {
  const match = /#(\d+)\s*$/.exec(tag);
  return match ? Number(match[1]) : 0;
}

function tagType(tag: string): string {
  return tag.replace(/\s*#\d+\s*$/, "").trim().toLowerCase();
}

function labelsMatch(a: string, b: string): boolean {
  const left = a.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const right = b.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

function centerDistance(a: Box, b: Box): number {
  const ay = (a[0] + a[2]) / 2;
  const ax = (a[1] + a[3]) / 2;
  const by = (b[0] + b[2]) / 2;
  const bx = (b[1] + b[3]) / 2;
  return Math.hypot(ax - bx, ay - by);
}

function iou(a: Box, b: Box): number {
  const top = Math.max(a[0], b[0]);
  const left = Math.max(a[1], b[1]);
  const bottom = Math.min(a[2], b[2]);
  const right = Math.min(a[3], b[3]);
  const intersection = Math.max(0, bottom - top) * Math.max(0, right - left);
  const areaA = Math.max(0, a[2] - a[0]) * Math.max(0, a[3] - a[1]);
  const areaB = Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
  const union = areaA + areaB - intersection;
  return union <= 0 ? 0 : intersection / union;
}
