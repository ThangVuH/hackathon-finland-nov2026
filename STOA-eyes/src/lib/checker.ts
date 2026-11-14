/** Scope, question type, and the agreement rule. The site runs this itself.

The trained detector is optional. When it is absent, a window or door count
still comes back from the vision model and stays unchecked.
*/

import type { RawAnalysis, RawItem } from "./detections";

export type QuestionType = "window" | "door" | "both" | "other";

export interface CheckerItem {
  kind?: string;
  label?: string;
  ymin: number;
  xmin: number;
  ymax: number;
  xmax: number;
  score?: number | null;
}

export interface VisionPayload {
  available: boolean;
  answer?: string;
  object_type?: string;
  count?: number;
  error?: string;
  items?: CheckerItem[];
}

const MATCH_IOU = 0.3;
const LABEL: Record<"window" | "door", string> = { window: "Window", door: "Door" };
const PLURAL: Record<"window" | "door", string> = { window: "windows", door: "doors" };

const VECTOR_EXTENSIONS = new Set([".dwg", ".dxf"]);
const SHEET_EXTENSIONS = new Set<string>();
const SOURCE_MARKERS = ["/habs/", "/finna/", "/europeana/", "/wikimedia/", "/ifc_models/", "/ifc-models/", "ifc_models", "ifc-models"];
const NAME_MARKERS = ["_sheet_", "-sheet-", "_sheet.", "-sheet.", "planche"];

function fold(text: string): string {
  return text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function askedKinds(question: string): Array<"window" | "door"> {
  const text = fold(question);
  const found: Array<"window" | "door"> = [];
  if (/\b(windows?|fenetres?|ikkuna\w*|finestr\w*|fenster\w*|vindue\w*|aken\w*)\b/.test(text)) found.push("window");
  if (/\b(doors?|portes?|ovea|ovia|ovi|turen|dore\w*|ust)\b/.test(text)) found.push("door");
  return found;
}

const DEMO_ROUTES: Record<string, string> = {
  "¿Cuántas ventanas se ven en esta planta?": "window",
  "Hur många dörrar finns inritade på den här ritningen?": "door",
  "Hoeveel deuren staan er op deze plattegrond?": "door",
  "Ile okien widać na tym rzucie kondygnacji?": "window",
  "¿Cuál es la superficie neta de la habitación 2.10?": "room_area",
  "Hur stor är den sammanlagda ytan för rum märkta Zimmer?": "labelled_area",
  "Wat is de netto-oppervlakte van appartement A?": "apartment_area",
  "Jaki jest numer telefonu architekta?": "aucun",
};

export function routeQuestion(question: string): { template: string; proof: string; cached: boolean } {
  const demo = DEMO_ROUTES[question];
  if (demo === "aucun") return { template: "unverified", proof: "unverified_vlm", cached: true };
  if (demo === "window" || demo === "door") return { template: demo, proof: "detector_boxes", cached: true };
  if (demo) return { template: demo, proof: "room_polygons", cached: true };
  const text = question.toLowerCase();
  const finish = (template: string, proof: string) => ({ template, proof, cached: false });
  const area = /net floor area|net area|superficie netta|surface nette|nettofläche|nettowohnfläche|nettoareal|netopõrandapind|nettovolumen|netto-volumen/.test(text);
  const code = question.replaceAll("’", "'").replaceAll("‘", "'").match(/\b[A-Za-z]*\d+\.\d+\b/);
  const letter = question.match(/(?:apartment|appartamento|appartement|wohnung)\s+([A-Za-z])\b/i);
  if (code && area && /room |locale |pièce |piece |raum |rummet/.test(text)) return finish("room_area", "room_polygons");
  if (letter && area) return finish("apartment_area", "room_polygons");
  if (area && /labelled|denominat|désign|design|bezeichn/.test(text)) return finish("labelled_area", "room_polygons");
  if (/numbered indoor|interni numerati|intérieures numérot|interieures numerot|nummerierten innen/.test(text)) {
    return finish("indoor_total", "room_polygons");
  }
  if (/rooms labelled|denominazione|bezeichnung|désignation|designation/.test(text)) return finish("label_count", "text_boxes");
  if (/apartments|appartamenti|appartements|wohnungen/.test(text) && !area) return finish("apartment_count", "text_boxes");
  if (/sinks and wash|pesu- ja tiskiallasta/.test(text)) return finish("sink", "detector_boxes");
  if (/showers and bathtub|suihkua ja kylpyammetta/.test(text)) return finish("shower", "detector_boxes");
  if (/bathtub|vasche da bagno|badewanne|baignoire/.test(text)) return finish("bath", "detector_boxes");
  if (/toilet bowl|wc seat|wc-istuin/.test(text)) return finish("toilet_bowl", "detector_boxes");
  if (/washbasin|lavabi|lavabo/.test(text)) return finish("basin", "detector_boxes");
  if (/toilet| wc|wcs/.test(text)) return finish("toilet", "detector_boxes");
  if (/kitchen|keittiö|keittio/.test(text)) return finish("kitchen", "detector_boxes");
  if (/sauna/.test(text)) return finish("sauna", "detector_boxes");
  if (/floors|storeys|kerrosta/.test(text)) return finish("floor", "detector_boxes");
  if (/net floor area of the room|nettoarealet af rummet|ruumi /.test(text)) return finish("ifc_room", "file_quantity");
  const kinds = askedKinds(question);
  if (kinds.length === 1) return finish(kinds[0]!, "detector_boxes");
  if (kinds.length === 2) return finish("both", "detector_boxes");
  return finish("unverified", "unverified_vlm");
}

const MEASURED: Record<string, string> = {
  window: "5 exact on 27. The constant was 1/27. On pixels alone, an exact count stays hard, and the badge says so.",
  door: "On 19 plans, 5 exact. The constant was 0/19.",
  sink: "On 27 plans, 10 exact. The constant was 10/27.",
  toilet: "On 26 plans, 16 exact. The constant was 12/26.",
  shower: "On 27 plans, 4 exact. The constant was 14/27.",
  sauna: "On 13 plans, 8 exact. The constant was 7/13. Non-modal plans: 6/6.",
};

export function measuredSentence(template: string): string {
  return MEASURED[template] ?? "";
}

export function recognizedTemplate(question: string): RawAnalysis | null {
  const routed = routeQuestion(question);
  if (routed.template === "window" || routed.template === "door" || routed.template === "both" || routed.template === "unverified") return null;
  if (routed.template === "sink" || routed.template === "toilet" || routed.template === "toilet_bowl" || routed.template === "shower" || routed.template === "sauna") return null;
  if (routed.template === "ifc_room") {
    return {
      answer: "Drop the IFC file. Each room is then listed with its name, value and GlobalId.",
      object_type: "Room",
      count: 0,
      items: [],
      verdict: "unverified",
      warning: "No count was invented.",
    };
  }
  return {
    answer: `Recognized template: ${routed.template}. The proof would be ${routed.proof.replaceAll("_", " ")}. No count was invented.`,
    object_type: routed.template,
    count: 0,
    items: [],
    verdict: "unverified",
    warning: routed.proof === "detector_boxes" ? "Detector boxes for this class stay unverified until the 27-plan score." : "This template is recognized, and it is not counted in the browser yet.",
  };
}

export function questionType(question: string): QuestionType {
  const kinds = askedKinds(question);
  if (kinds.length === 2) return "both";
  if (kinds.length === 1) return kinds[0]!;
  return "other";
}

function kindOf(value: string): "window" | "door" | null {
  const kinds = askedKinds(value);
  return kinds.length === 1 ? kinds[0]! : null;
}

function extensionOf(filename: string): string {
  const leaf = filename.split("/").pop() ?? filename;
  const dot = leaf.lastIndexOf(".");
  return dot >= 0 ? leaf.slice(dot) : "";
}

/** Filename rules only. A dark floor plan stays in scope. */
export function nameReason(filename: string | undefined): string | null {
  const text = (filename || "drawing.png").replaceAll("\\", "/").toLowerCase();
  const extension = extensionOf(text);
  if (VECTOR_EXTENSIONS.has(extension)) {
    return "CAD file. The checker reads a floor-plan image, a PDF or an IFC file, and it will not invent a count for this file.";
  }
  if (SHEET_EXTENSIONS.has(extension)) {
    return "Drawing sheet (PDF). The checker reads one floor plan, not a title-block sheet, and it will not invent a count.";
  }
  const padded = `/${text}`;
  if (SOURCE_MARKERS.some((marker) => padded.includes(marker))) {
    return "Archive scan or IFC export. Outside the floor plans this detector was trained on, so no count is returned.";
  }
  const leaf = text.split("/").pop() ?? text;
  if (NAME_MARKERS.some((marker) => leaf.includes(marker))) {
    return "This filename is an archive sheet. The checker does not count photographed drawing sheets.";
  }
  return null;
}

function iou(a: number[], b: number[]): number {
  const width = Math.max(0, Math.min(a[2]!, b[2]!) - Math.max(a[0]!, b[0]!));
  const height = Math.max(0, Math.min(a[3]!, b[3]!) - Math.max(a[1]!, b[1]!));
  const inter = width * height;
  if (inter === 0) return 0;
  const areaA = Math.max(0, a[2]! - a[0]!) * Math.max(0, a[3]! - a[1]!);
  const areaB = Math.max(0, b[2]! - b[0]!) * Math.max(0, b[3]! - b[1]!);
  return inter / (areaA + areaB - inter);
}

function xyxy(item: CheckerItem): number[] {
  return [item.xmin, item.ymin, item.xmax, item.ymax];
}

function itemKind(item: CheckerItem): "window" | "door" | null {
  return kindOf(item.kind || "") || kindOf(item.label || "");
}

function matchIndices(detector: CheckerItem[], vision: CheckerItem[], threshold = MATCH_IOU): Set<string> {
  const order = detector.map((_, index) => index).sort((a, b) => (detector[b]?.score ?? 0) - (detector[a]?.score ?? 0));
  const used = new Set<number>();
  const pairs = new Set<string>();
  for (const index of order) {
    let best: number | null = null;
    let bestOverlap = threshold;
    const box = xyxy(detector[index]!);
    vision.forEach((candidate, other) => {
      if (used.has(other)) return;
      const overlap = iou(box, xyxy(candidate));
      if (overlap >= bestOverlap) {
        bestOverlap = overlap;
        best = other;
      }
    });
    if (best !== null) {
      used.add(best);
      pairs.add(`${index}:${best}`);
    }
  }
  return pairs;
}

function classItems(items: CheckerItem[], kind: "window" | "door"): CheckerItem[] {
  return items.filter((item) => itemKind(item) === kind);
}

function copyItem(
  item: CheckerItem,
  flags: { kind: string; label?: string; source: "detector" | "vision" | "both"; disputed: boolean; included: boolean },
): RawItem {
  return {
    kind: flags.kind,
    label: flags.label ?? item.label ?? "",
    ymin: Math.trunc(item.ymin),
    xmin: Math.trunc(item.xmin),
    ymax: Math.trunc(item.ymax),
    xmax: Math.trunc(item.xmax),
    source: flags.source,
    disputed: flags.disputed,
    included: flags.included,
  };
}

function sentence(kind: "window" | "door", detectorCount: number, visionCount: number | null, agreed: boolean, visionMissing: boolean): string {
  const plural = PLURAL[kind];
  if (visionMissing) {
    return `The detector counts ${detectorCount} ${plural}. The vision model did not confirm it, so this stays unchecked.`;
  }
  if (agreed) {
    return `Both engines count ${detectorCount} ${plural}, and the boxes overlap. This count is reliable.`;
  }
  const visionText = visionCount === null ? "no answer" : String(visionCount);
  return `The detector counts ${detectorCount} ${plural}; the vision model counts ${visionText}. Highlighted boxes are the disagreement. Click one to keep it or drop it.`;
}

function unverified(vision: VisionPayload | null): RawAnalysis {
  if (!vision?.available) {
    return {
      answer: vision?.error || "The vision model is not configured, and this question is outside windows and doors.",
      object_type: "",
      count: 0,
      items: [],
      verdict: "refused",
      warning: "No count was invented.",
    };
  }
  const items = (vision.items ?? []).map((item) =>
    copyItem(item, {
      kind: item.kind || vision.object_type || "",
      source: "vision",
      disputed: false,
      included: true,
    }),
  );
  return {
    answer: (vision.answer || "").trim(),
    object_type: vision.object_type || "",
    count: items.length > 0 ? items.length : Math.trunc(vision.count || 0),
    items,
    verdict: "unverified",
    warning: "Windows and doors are the classes the detector checks. This answer is the vision model alone.",
  };
}

export function arbitrate(
  questionType: string,
  detectorItems: CheckerItem[],
  confidence: number,
  vision: VisionPayload | null,
): RawAnalysis {
  if (questionType === "other") return unverified(vision);

  const kinds: Array<"window" | "door"> = questionType === "both" ? ["window", "door"] : [questionType as "window" | "door"];
  const visionItems = [...(vision?.items ?? [])];
  const visionMissing = !vision?.available;
  if (visionItems.length > 0 && vision?.object_type && !visionItems.some((item) => itemKind(item))) {
    for (const item of visionItems) item.kind = vision.object_type;
  }

  const merged: RawItem[] = [];
  const sentences: string[] = [];
  const scores: number[] = [];
  let agreedAll = true;
  for (const kind of kinds) {
    const detected = classItems(detectorItems, kind);
    const seen = visionMissing ? [] : classItems(visionItems, kind);
    const pairs = visionMissing ? new Set<string>() : matchIndices(detected, seen);
    const matchedDetector = new Set([...pairs].map((pair) => Number(pair.split(":")[0])));
    const matchedVision = new Set([...pairs].map((pair) => Number(pair.split(":")[1])));
    const matched = pairs.size;
    const score = visionMissing
      ? 0
      : detected.length !== seen.length
        ? Math.min(0.5, (matched / Math.max(detected.length, seen.length, 1)) * 0.5)
        : detected.length === 0
          ? 1
          : matched / detected.length;
    scores.push(score);
    const agreed = score >= 1;
    agreedAll = agreedAll && agreed;
    detected.forEach((item, index) => {
      merged.push(
        copyItem(item, {
          kind,
          source: matchedDetector.has(index) ? "both" : "detector",
          disputed: !matchedDetector.has(index),
          included: true,
        }),
      );
    });
    seen.forEach((item, index) => {
      if (matchedVision.has(index)) return;
      merged.push(
        copyItem(item, {
          kind,
          label: item.label || LABEL[kind],
          source: "vision",
          disputed: true,
          included: false,
        }),
      );
    });
    sentences.push(sentence(kind, detected.length, visionMissing ? null : seen.length, agreed, visionMissing));
  }

  const included = merged.filter((item) => item.included !== false).length;
  const verdict = agreedAll ? "reliable" : "review";
  let warning = verdict === "reliable" ? "" : "Click a highlighted box to keep it in the count or drop it.";
  if (visionMissing) warning = "The vision model did not answer, so the detector count is not confirmed.";
  return {
    answer: sentences.join(" "),
    object_type: questionType === "both" ? "Opening" : LABEL[questionType as "window" | "door"],
    count: included,
    items: merged,
    verdict,
    warning,
    confidence: Math.round(confidence * 10000) / 10000,
  };
}

/** Window or door question when this machine is not running the trained detector. */
export function withoutDetector(kind: QuestionType, vision: VisionPayload | null): RawAnalysis {
  if (kind === "other") return arbitrate("other", [], 0, vision);
  if (!vision?.available) {
    return {
      answer: "The AI service isn't configured, and the trained detector is not running on this machine.",
      object_type: "",
      count: 0,
      items: [],
      verdict: "refused",
      warning: "No count was invented.",
    };
  }
  const alone = arbitrate("other", [], 0, vision);
  return {
    ...alone,
    warning: "The trained detector is not running, so this count is the vision model alone and is not cross-checked.",
  };
}
