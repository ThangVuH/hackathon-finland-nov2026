/** Drawing backend. A configured model key is used when present. Otherwise the sample sheets are answered locally so the app can be tested without waiting on another service. */

import type { RawAnalysis } from "./detections";

export type BackendKind = "openai" | "lovable" | "local";

export interface BackendInfo {
  kind: BackendKind;
  label: string;
  model?: string;
  apiKey?: string;
  baseURL?: string;
}

type Box = [ymin: number, xmin: number, ymax: number, xmax: number];
type Item = { label: string; box: Box };
type SheetId = "office" | "apartment";

export function selectBackend(env: Record<string, string | undefined>): BackendInfo {
  const ownKey = env["STOA_API_KEY"] || env["OPENAI_API_KEY"];
  if (ownKey) {
    const model = env["STOA_MODEL"] || "gpt-4o-mini";
    return {
      kind: "openai",
      apiKey: ownKey,
      baseURL: env["STOA_API_BASE"] || "https://api.openai.com/v1",
      model,
      label: `Model · ${model}`,
    };
  }
  if (env["LOVABLE_API_KEY"]) {
    return {
      kind: "lovable",
      apiKey: env["LOVABLE_API_KEY"],
      baseURL: "https://ai.gateway.lovable.dev/v1",
      model: "openai/gpt-6-astra",
      label: "Model · Lovable",
    };
  }
  return { kind: "local", label: "Local backend · sample sheets" };
}

export function sheetIdFromName(name: string | undefined): SheetId | null {
  if (!name) return null;
  const normalized = name.toLowerCase();
  if (normalized.includes("a-201") || normalized.includes("office")) return "office";
  if (normalized.includes("a-101") || normalized.includes("apartment") || normalized.includes("2br")) return "apartment";
  return null;
}

export function answerSampleSheet(sheetName: string | undefined, question: string): RawAnalysis | null {
  const sheet = sheetIdFromName(sheetName);
  if (!sheet) return null;
  const kind = questionKind(question);
  const catalog = sheet === "office" ? OFFICE : APARTMENT;
  if (!kind || !catalog[kind]) {
    return {
      answer: "The local backend counts doors, windows, rooms, and columns on the sample sheets.",
      object_type: "",
      count: 0,
      items: [],
    };
  }
  return pack(kind, catalog[kind]);
}

export function localMissError(): string {
  return "This drawing is not covered by the local backend. Add STOA_API_KEY in .env to analyze other sheets.";
}

function questionKind(question: string): "window" | "door" | "column" | "stair" | "room" | null {
  const q = question.toLowerCase();
  if (/\bwindows?\b/.test(q)) return "window";
  if (/\bdoors?\b/.test(q)) return "door";
  if (/\bcolumns?\b/.test(q)) return "column";
  if (/\bstairs?\b/.test(q)) return "stair";
  if (/\brooms?\b/.test(q)) return "room";
  return null;
}

function pack(kind: string, items: Item[]): RawAnalysis {
  const noun = kind === "stair" ? "stair" : kind;
  const answer =
    items.length === 0
      ? `No ${noun}s are drawn on this sheet.`
      : `${items.length} ${noun}${items.length === 1 ? "" : "s"} on this sheet.`;
  return {
    answer,
    object_type: noun.charAt(0).toUpperCase() + noun.slice(1),
    count: items.length,
    items: items.map((item) => ({
      label: item.label,
      kind: noun,
      ymin: item.box[0],
      xmin: item.box[1],
      ymax: item.box[2],
      xmax: item.box[3],
    })),
  };
}

const at = (label: string, ymin: number, xmin: number, ymax: number, xmax: number): Item => ({
  label,
  box: [ymin, xmin, ymax, xmax],
});

const OFFICE: Record<string, Item[]> = {
  room: [
    at("Office 1", 145, 95, 360, 300),
    at("Office 2", 145, 300, 360, 500),
    at("Office 3", 145, 500, 360, 680),
    at("Meeting room", 145, 680, 360, 910),
    at("Open workspace", 360, 95, 800, 680),
    at("Restroom", 380, 700, 560, 910),
    at("Stair", 560, 700, 800, 910),
  ],
  door: [
    at("Office 1 door", 330, 210, 390, 280),
    at("Office 2 door", 330, 400, 390, 470),
    at("Office 3 door", 330, 530, 390, 600),
    at("Meeting room door", 330, 700, 390, 770),
    at("Restroom door", 470, 680, 540, 750),
    at("Stair door", 620, 680, 700, 760),
    at("Main entrance", 760, 420, 840, 560),
  ],
  window: [
    at("Office 1 window", 125, 150, 155, 250),
    at("Office 2 window", 125, 350, 155, 450),
    at("Office 3 window", 125, 540, 155, 640),
    at("Meeting room window", 125, 740, 155, 860),
    at("West window", 500, 70, 580, 100),
    at("South window", 800, 180, 830, 300),
    at("East window", 640, 890, 720, 920),
    at("Entrance sidelight", 800, 560, 830, 660),
  ],
  column: gridMarks(
    [120, 380, 640, 900],
    [160, 400, 640, 860],
  ),
  stair: [at("Stair", 560, 700, 800, 910)],
};

const APARTMENT: Record<string, Item[]> = {
  room: [
    at("Living", 150, 90, 520, 470),
    at("Bedroom 1", 150, 470, 470, 720),
    at("Bedroom 2", 150, 720, 470, 910),
    at("Kitchen", 520, 90, 780, 470),
    at("Bath", 520, 680, 780, 910),
  ],
  door: [
    at("Bedroom 1 door", 430, 520, 510, 620),
    at("Bedroom 2 door", 430, 740, 510, 840),
    at("Kitchen door", 740, 400, 830, 500),
    at("Bath door", 500, 680, 600, 780),
  ],
  window: [
    at("Living window", 130, 160, 165, 380),
    at("Bedroom 1 window", 130, 520, 165, 680),
    at("Bedroom 2 window", 130, 740, 165, 880),
  ],
  column: [],
  stair: [],
};

function gridMarks(xs: number[], ys: number[]): Item[] {
  const items: Item[] = [];
  for (const y of ys) {
    for (const x of xs) {
      items.push(at("Column", y - 14, x - 14, y + 14, x + 14));
    }
  }
  return items;
}
