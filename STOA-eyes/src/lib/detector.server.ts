/** Calls the local counting service. The browser never talks to it directly. */

import { Buffer } from "node:buffer";

import type { RawAnalysis } from "./detections";

const DETECTOR_URL = process.env["DETECTOR_URL"] ?? "http://127.0.0.1:8765";

export interface DetectorBody {
  ok: boolean;
  error?: string;
  scope: "floor_plan" | "out_of_scope";
  question_type: "window" | "door" | "both" | "other";
  reason: string;
  confidence: number;
  items: {
    kind: string;
    label: string;
    ymin: number;
    xmin: number;
    ymax: number;
    xmax: number;
    score: number | null;
  }[];
}

export function dataUrlToBlob(dataUrl: string): Blob {
  const match = /^data:(.*?);base64,(.*)$/.exec(dataUrl);
  if (!match?.[2]) throw new Error("The drawing could not be encoded.");
  const bytes = Uint8Array.from(Buffer.from(match[2], "base64"));
  return new Blob([bytes], { type: match[1] || "image/jpeg" });
}

export async function callDetector(input: {
  imageDataUrl: string;
  question: string;
  filename?: string;
}): Promise<{ ok: true; body: DetectorBody } | { ok: false; error: string }> {
  const form = new FormData();
  form.set("file", dataUrlToBlob(input.imageDataUrl), input.filename || "drawing.jpg");
  form.set("question", input.question);
  let response: Response;
  try {
    response = await fetch(`${DETECTOR_URL}/detect`, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(180_000),
    });
  } catch (error) {
    console.error("[stoa-checker] detector unreachable", error);
    return {
      ok: false,
      error: "The counting service is not running. Start it with: py -3.13 -m uvicorn server:app --port 8765",
    };
  }
  if (!response.ok) return { ok: false, error: "The counting service rejected the drawing." };
  const body = (await response.json()) as DetectorBody;
  if (!body.ok) return { ok: false, error: body.error || body.reason || "The counting service could not read this drawing." };
  return { ok: true, body };
}

export async function callArbitrate(input: {
  questionType: DetectorBody["question_type"];
  detectorItems: DetectorBody["items"];
  confidence: number;
  vision: Record<string, unknown> | null;
}): Promise<{ ok: true; raw: RawAnalysis } | { ok: false; error: string }> {
  let response: Response;
  try {
    response = await fetch(`${DETECTOR_URL}/arbitrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_type: input.questionType,
        detector_items: input.detectorItems,
        confidence: input.confidence,
        vision: input.vision,
      }),
      signal: AbortSignal.timeout(30_000),
    });
  } catch (error) {
    console.error("[stoa-checker] arbitrate unreachable", error);
    return { ok: false, error: "The counting service is not running, so the two answers could not be compared." };
  }
  if (!response.ok) return { ok: false, error: "The comparison of the two counts failed." };
  const raw = (await response.json()) as RawAnalysis;
  return { ok: true, raw };
}
