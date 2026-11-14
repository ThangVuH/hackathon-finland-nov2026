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
