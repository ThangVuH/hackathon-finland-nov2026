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
}): Promise<{ ok: true; body: DetectorBody } | { ok: false; unavailable: boolean; error: string }> {
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
  } catch {
    console.warn("[stoa-checker] trained detector is not running; the answer will not be cross-checked");
    return {
      ok: false,
      unavailable: true,
      error: "The counting service is not running.",
    };
  }
  if (!response.ok) return { ok: false, unavailable: false, error: "The counting service rejected the drawing." };
  const body = (await response.json()) as DetectorBody;
  if (!body.ok) return { ok: false, unavailable: false, error: body.error || body.reason || "The counting service could not read this drawing." };
  return { ok: true, body };
}

export async function callFileReader(input: {
  imageDataUrl: string;
  question: string;
  filename?: string;
}): Promise<{ ok: true; body: RawAnalysis & { preview?: string; ok?: boolean } } | { ok: false; error: string }> {
  const form = new FormData();
  form.set("file", dataUrlToBlob(input.imageDataUrl), input.filename || "drawing.pdf");
  form.set("question", input.question);
  try {
    const response = await fetch(`${DETECTOR_URL}/file`, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(180_000),
    });
    if (!response.ok) return { ok: false, error: "The file reader rejected this drawing." };
    const body = (await response.json()) as RawAnalysis & { preview?: string; ok?: boolean };
    if (body.ok === false) return { ok: false, error: body.answer || "The file reader could not read this drawing." };
    return { ok: true, body };
  } catch {
    return { ok: false, error: "The counting service is not running, so this file was not read." };
  }
}
