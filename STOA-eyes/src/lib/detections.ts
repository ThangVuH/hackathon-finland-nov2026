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
  items: { label: string; ymin: number; xmin: number; ymax: number; xmax: number }[];
}

const clamp = (n: number) => Math.min(1000, Math.max(0, Math.round(Number.isFinite(n) ? n : 0)));

function titleCase(s: string) {
  const t = s.trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "Item";
}

/** Clamps to 0-1000, fixes inverted corners, drops zero-area boxes and numbers each item. */
export function normalizeAnalysis(raw: RawAnalysis): AnalysisResult {
  const objectType = titleCase(raw.object_type || "Item");
  const detections: Detection[] = [];
  for (const item of raw.items ?? []) {
    let ymin = clamp(item.ymin);
    let xmin = clamp(item.xmin);
    let ymax = clamp(item.ymax);
    let xmax = clamp(item.xmax);
    if (ymin > ymax) [ymin, ymax] = [ymax, ymin];
    if (xmin > xmax) [xmin, xmax] = [xmax, xmin];
    if (ymax - ymin < 1 || xmax - xmin < 1) continue;
    detections.push({
      tag: `${objectType} #${detections.length + 1}`,
      label: (item.label || "").trim(),
      box: [ymin, xmin, ymax, xmax],
    });
  }
  const count = detections.length > 0 ? detections.length : Math.max(0, Math.round(raw.count || 0));
  return { answer: raw.answer.trim(), objectType, count, detections };
}

/** Keep the number and name an item received the first time it was found on this sheet. */
export function stabilizeDetections(known: Detection[], result: AnalysisResult): AnalysisResult {
  const type = result.objectType.trim().toLowerCase();
  const prior = known.filter((item) => tagType(item.tag) === type);
  const used = new Set<number>();
  const pairs: { index: number; priorIndex: number; score: number }[] = [];
  result.detections.forEach((item, index) => {
    prior.forEach((earlier, priorIndex) => {
      const overlap = iou(item.box, earlier.box);
      const sameName = labelsMatch(item.label, earlier.label);
      const close = centerDistance(item.box, earlier.box) <= 80;
      if (overlap < 0.2 && !(sameName && (close || overlap >= 0.05))) return;
      pairs.push({ index, priorIndex, score: overlap + (sameName ? 0.5 : 0) });
    });
  });
  pairs.sort((a, b) => b.score - a.score);
  const takenNew = new Set<number>();
  const takenPrior = new Set<number>();
  const matched = new Map<number, Detection>();
  for (const pair of pairs) {
    if (takenNew.has(pair.index) || takenPrior.has(pair.priorIndex)) continue;
    const earlier = prior[pair.priorIndex]!;
    const item = result.detections[pair.index]!;
    takenNew.add(pair.index);
    takenPrior.add(pair.priorIndex);
    used.add(tagNumber(earlier.tag));
    matched.set(pair.index, {
      tag: earlier.tag,
      label: earlier.label || item.label,
      box: item.box,
    });
  }
  let next = prior.reduce((max, item) => Math.max(max, tagNumber(item.tag)), 0);
  const detections = result.detections.map((item, index) => {
    const kept = matched.get(index);
    if (kept) return kept;
    next += 1;
    while (used.has(next)) next += 1;
    used.add(next);
    return { ...item, tag: `${result.objectType} #${next}` };
  });
  detections.sort((a, b) => tagNumber(a.tag) - tagNumber(b.tag));
  return { ...result, detections };
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
