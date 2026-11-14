/** Nano Banana redraws a complicated sheet into a clean plan before the counting pipeline runs. */

export const SIMPLIFY_PROMPT = `This is one construction drawing. In one short sentence, say what kind of drawing it is. Then redraw only that drawing as a clean plan: white paper, black lines, the same walls, doors, windows, rooms, stairs, and columns in the same places. Keep each room name as plain text. Remove dimensions, title blocks, north arrows, hatching, shadows, and pencil smudges. Do not add rooms, furniture, or labels that are not on the sheet.`;

const ASPECTS: { name: string; ratio: number }[] = [
  { name: "1:1", ratio: 1 },
  { name: "4:3", ratio: 4 / 3 },
  { name: "3:4", ratio: 3 / 4 },
  { name: "3:2", ratio: 3 / 2 },
  { name: "2:3", ratio: 2 / 3 },
  { name: "16:9", ratio: 16 / 9 },
  { name: "9:16", ratio: 9 / 16 },
];

export function nearestAspectRatio(width: number, height: number): string {
  const ratio = width / Math.max(1, height);
  let best = ASPECTS[0]!;
  let bestGap = Number.POSITIVE_INFINITY;
  for (const aspect of ASPECTS) {
    const gap = Math.abs(Math.log(ratio) - Math.log(aspect.ratio));
    if (gap < bestGap) {
      best = aspect;
      bestGap = gap;
    }
  }
  return best.name;
}

export function readBananaImage(payload: unknown): { imageDataUrl: string; note: string } | null {
  if (!payload || typeof payload !== "object") return null;
  const candidates = (payload as { candidates?: unknown }).candidates;
  if (!Array.isArray(candidates)) return null;
  const parts = candidates.flatMap((candidate) => {
    const content = (candidate as { content?: { parts?: unknown[] } }).content;
    return Array.isArray(content?.parts) ? content.parts : [];
  });
  let note = "";
  let image: { mime: string; data: string } | null = null;
  for (const part of parts) {
    if (!part || typeof part !== "object") continue;
    const record = part as Record<string, unknown>;
    if (record.thought === true) continue;
    if (typeof record.text === "string" && record.text.trim()) note = record.text.trim();
    const inline = (record.inlineData ?? record.inline_data) as Record<string, unknown> | undefined;
    if (!inline || typeof inline.data !== "string" || inline.data.length < 32) continue;
    const mime =
      typeof inline.mimeType === "string"
        ? inline.mimeType
        : typeof inline.mime_type === "string"
          ? inline.mime_type
          : "image/png";
    image = { mime, data: inline.data.replace(/\s/g, "") };
  }
  if (!image) return null;
  const sentence = note.replace(/\s+/g, " ").slice(0, 220);
  return {
    imageDataUrl: `data:${image.mime};base64,${image.data}`,
    note: sentence || "Nano Banana redrew this sheet as a clean plan.",
  };
}
