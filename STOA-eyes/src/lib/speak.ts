import { detectionKind, type AnalysisResult, type Detection } from "./detections";

/** The sentence on screen. A bare count is expanded. A fuller reply from the model is kept. */
export function spokenAnswer(result: AnalysisResult): string {
  const written = result.answer.trim();
  if (written && !isBareCount(written)) return written;
  return describeFindings(result) || written;
}

function isBareCount(text: string): boolean {
  const sentences = text.split(/[.!?]/).map((part) => part.trim()).filter(Boolean);
  if (sentences.length >= 2) return false;
  return text.length < 90 && /^(there (are|is)|i (count|see|found)|no )\b/i.test(text);
}

function describeFindings(result: AnalysisResult): string {
  const groups = new Map<string, Detection[]>();
  for (const item of result.detections) {
    const kind = detectionKind(item.tag);
    groups.set(kind, [...(groups.get(kind) ?? []), item]);
  }
  if (groups.size === 0) {
    const noun = result.objectType.trim().toLowerCase() || "item";
    return result.count === 0 ? `I don't see any ${noun}s on this sheet.` : "";
  }
  if (groups.size === 1) {
    const [kind, items] = [...groups][0]!;
    return sentenceFor(kind, items);
  }
  return [...groups].map(([kind, items]) => sentenceFor(kind, items)).join(" ");
}

function sentenceFor(kind: string, items: Detection[]): string {
  const noun = kind === "object" ? "item" : kind;
  const count = items.length;
  const word = count === 1 ? noun : `${noun}s`;
  const lead = count === 1 ? `There is 1 ${noun} on this sheet.` : `There are ${count} ${word} on this sheet.`;
  const places = items.map(placeOf).filter(Boolean);
  if (places.length === 0) return lead;
  return `${lead} ${join(places)}.`;
}

function placeOf(item: Detection): string {
  const label = item.label.trim();
  if (!label) return item.tag;
  const named = /^(a|an|the)\b/i.test(label) ? label : `the ${label}`;
  return `${item.tag} is ${named}`;
}

function join(parts: string[]): string {
  if (parts.length === 1) return parts[0] ?? "";
  return `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
}
