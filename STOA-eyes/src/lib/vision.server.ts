import https from "node:https";

import { createOpenAI } from "@ai-sdk/openai";
import { APICallError, NoObjectGeneratedError, Output, jsonSchema, streamText, type ModelMessage } from "ai";

import { createLovableAiGatewayRunIdFetch } from "./ai/run-id.server";
import { answerSampleSheet, localMissError, selectBackend, type BackendInfo } from "./backend.server";
import { arbitrate, nameReason, questionType, withoutDetector, type VisionPayload } from "./checker";
import { callDetector } from "./detector.server";
import type { RawAnalysis } from "./detections";

const GATEWAY_URL = "https://ai.gateway.lovable.dev/v1";
const MODEL = "openai/gpt-6-astra";

const INSTRUCTIONS = `You are Stoa Vision, an expert construction site engineer and quantity surveyor reading architectural and construction drawings (floor plans, elevations, sections, MEP and structural layouts).

Answer the engineer's question about the attached drawing precisely and concisely.

When the question asks to count, locate, identify or list elements (doors, windows, rooms, columns, stairs, fixtures, etc.):
- Inspect the whole sheet systematically (left-to-right, top-to-bottom) and find EVERY instance.
- Doors: look for door leaves with swing arcs, sliding doors and openings with door symbols. A double door is ONE door.
- Windows: thin double/triple parallel lines set inside walls. Each separate window opening is one window.
- Rooms: enclosed labelled or clearly bounded spaces; box the full interior extent.
- Columns: small solid/hatched squares or circles on the structural grid.
- Return one item per instance with a tight bounding box [ymin, xmin, ymax, xmax] normalized to 0-1000, where 0,0 is the top-left of the image and 1000,1000 is the bottom-right (y = vertical, x = horizontal).
- "label" is a short location-aware descriptor, e.g. "Entry door, south wall" or "Bedroom 1".
- "object_type" is the singular element name, e.g. "Door", "Window", "Room", "Column".
- "count" equals the number of items. The "answer" must state the count and a one-line breakdown if useful.

For questions that do not need locations, answer in "answer", set object_type to "" and items to [].
Never invent elements that are not drawn. If the drawing is unreadable, say so.`;

const analysisSchema = jsonSchema<RawAnalysis>({
  type: "object",
  additionalProperties: false,
  required: ["answer", "object_type", "count", "items"],
  properties: {
    answer: { type: "string", description: "Concise answer for the engineer, 1-3 sentences." },
    object_type: { type: "string", description: "Singular element type counted, or empty string." },
    count: { type: "number" },
    items: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["label", "ymin", "xmin", "ymax", "xmax"],
        properties: {
          label: { type: "string" },
          ymin: { type: "number" },
          xmin: { type: "number" },
          ymax: { type: "number" },
          xmax: { type: "number" },
        },
      },
    },
  },
});

export interface AnalyzeInput {
  imageDataUrl: string;
  imageWidth: number;
  imageHeight: number;
  question: string;
  filename?: string;
  history: { role: "user" | "assistant"; text: string }[];
}

export type AnalyzeOutcome = { ok: true; raw: RawAnalysis } | { ok: false; error: string };

function describeError(error: unknown): string {
  if (APICallError.isInstance(error)) {
    const status = error.statusCode;
    if (status === 402) return "AI credits are used up for this workspace. Add credits to keep analyzing drawings.";
    if (status === 429) return "Too many requests right now. Wait a few seconds and try again.";
    if (status === 401) return "The AI service isn't configured correctly for this app.";
    if (status === 403) return safeMessage(error.responseBody) ?? "AI access is blocked for this workspace.";
    if (status === 400) return "The drawing couldn't be processed. Try a smaller or clearer image.";
    return "The AI service had a temporary problem. Please try again.";
  }
  if (NoObjectGeneratedError.isInstance(error)) {
    return "The AI returned an unreadable answer. Try rephrasing the question.";
  }
  return "Analysis failed unexpectedly. Please try again.";
}

function safeMessage(body: string | undefined) {
  if (!body) return undefined;
  try {
    const parsed = JSON.parse(body);
    return parsed?.error?.message ?? parsed?.message;
  } catch {
    return undefined;
  }
}

export function currentBackend(): BackendInfo {
  return selectBackend(process.env);
}

async function runVision(input: AnalyzeInput): Promise<AnalyzeOutcome> {
  const backend = selectBackend(process.env);
  if (backend.kind === "local") {
    const raw = answerSampleSheet(input.filename, input.question);
    return raw ? { ok: true, raw } : { ok: false, error: localMissError() };
  }
  if (backend.kind === "openai") {
    if ((backend.baseURL ?? "").includes("generativelanguage.googleapis.com")) return analyzeWithGemini(input, backend);
    return analyzeWithChatModel(input, backend);
  }

  const apiKey = backend.apiKey ?? "";
  const runIdFetch = createLovableAiGatewayRunIdFetch(undefined);
  const provider = createOpenAI({
    baseURL: GATEWAY_URL,
    apiKey,
    headers: { "Lovable-API-Key": apiKey, "X-Lovable-AIG-SDK": "vercel-ai-sdk" },
    fetch: runIdFetch.fetch,
  });

  const messages: ModelMessage[] = [
    ...input.history.slice(-8).map(
      (m): ModelMessage =>
        m.role === "user"
          ? { role: "user", content: m.text }
          : { role: "assistant", content: m.text },
    ),
    {
      role: "user",
      content: [
        {
          type: "text",
          text: `Drawing image is ${input.imageWidth} x ${input.imageHeight} px. Question: ${input.question}`,
        },
        { type: "image", image: new URL(input.imageDataUrl) },
      ],
    },
  ];

  try {
    const result = streamText({
      model: provider.responses(MODEL),
      instructions: INSTRUCTIONS,
      messages,
      output: Output.object({ schema: analysisSchema }),
      providerOptions: {
        openai: {
          forceReasoning: true,
          reasoningEffort: "medium",
          reasoningSummary: "auto",
          store: false,
          include: ["reasoning.encrypted_content"],
        },
      },
    });
    // Drain the stream server-side; surface any streamed error.
    let streamError: unknown;
    for await (const part of result.fullStream) {
      if (part.type === "error") streamError = part.error;
    }
    if (streamError) throw streamError;
    const raw = await result.output;
    return { ok: true, raw };
  } catch (error) {
    console.error("[stoa-vision] analysis failed", error);
    return { ok: false, error: describeError(error) };
  }
}

function refused(reason: string): RawAnalysis {
  return {
    answer: reason,
    object_type: "",
    count: 0,
    items: [],
    verdict: "refused",
    warning: "Out of scope. No count was invented.",
  };
}

export async function analyzeDrawingOnServer(input: AnalyzeInput): Promise<AnalyzeOutcome> {
  const refusedName = nameReason(input.filename);
  if (refusedName) return { ok: true, raw: refused(refusedName) };

  const detected = await callDetector(input);
  if (detected.ok && detected.body.scope === "out_of_scope") return { ok: true, raw: refused(detected.body.reason) };

  const vision = await runVision(input);
  const visionPayload: VisionPayload = vision.ok
    ? { available: true, answer: vision.raw.answer, object_type: vision.raw.object_type, count: vision.raw.count, items: vision.raw.items }
    : { available: false, error: vision.error, items: [] };

  if (!detected.ok) {
    if (!detected.unavailable) return detected;
    const kind = questionType(input.question);
    if (!vision.ok && kind === "other") return vision;
    return { ok: true, raw: withoutDetector(kind, visionPayload) };
  }

  if (detected.body.question_type === "other" && !vision.ok) return vision;

  return {
    ok: true,
    raw: arbitrate(detected.body.question_type, detected.body.items, detected.body.confidence, visionPayload),
  };
}

async function analyzeWithChatModel(input: AnalyzeInput, backend: BackendInfo): Promise<AnalyzeOutcome> {
  const provider = createOpenAI({
    ...(backend.baseURL ? { baseURL: backend.baseURL } : {}),
    ...(backend.apiKey ? { apiKey: backend.apiKey } : {}),
  });
  const messages: ModelMessage[] = [
    ...input.history.slice(-8).map(
      (m): ModelMessage => (m.role === "user" ? { role: "user", content: m.text } : { role: "assistant", content: m.text }),
    ),
    {
      role: "user",
      content: [
        { type: "text", text: `Drawing image is ${input.imageWidth} x ${input.imageHeight} px. Question: ${input.question}` },
        { type: "image", image: new URL(input.imageDataUrl) },
      ],
    },
  ];
  try {
    const result = streamText({
      model: provider.chat(backend.model ?? "gpt-4o-mini"),
      instructions: INSTRUCTIONS,
      messages,
      maxRetries: 1,
      timeout: 120_000,
      output: Output.object({ schema: analysisSchema }),
    });
    let streamError: unknown;
    for await (const part of result.fullStream) {
      if (part.type === "error") streamError = part.error;
    }
    if (streamError) throw streamError;
    const raw = await result.output;
    return { ok: true, raw };
  } catch (error) {
    console.error("[stoa-vision] analysis failed", error);
    return { ok: false, error: describeError(error) };
  }
}

const GEMINI_SCHEMA = {
  type: "OBJECT",
  required: ["answer", "object_type", "count", "items"],
  properties: {
    answer: { type: "STRING" },
    object_type: { type: "STRING" },
    count: { type: "INTEGER" },
    items: {
      type: "ARRAY",
      items: {
        type: "OBJECT",
        required: ["label", "ymin", "xmin", "ymax", "xmax"],
        properties: {
          label: { type: "STRING" },
          ymin: { type: "NUMBER" },
          xmin: { type: "NUMBER" },
          ymax: { type: "NUMBER" },
          xmax: { type: "NUMBER" },
        },
      },
    },
  },
};

/** Gemini's own generateContent endpoint. The OpenAI-compatible route kept the connection open and never sent a reply. */
async function analyzeWithGemini(input: AnalyzeInput, backend: BackendInfo): Promise<AnalyzeOutcome> {
  const image = dataUrlParts(input.imageDataUrl);
  if (!image) return { ok: false, error: "The drawing couldn't be prepared for analysis." };
  const model = backend.model || "gemini-2.5-flash";
  const models = [model];
  for (const fallback of ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]) {
    if (!models.includes(fallback)) models.push(fallback);
  }
  const contents = [
    ...input.history.slice(-8).map((message) => ({
      role: message.role === "assistant" ? "model" : "user",
      parts: [{ text: message.text }],
    })),
    {
      role: "user",
      parts: [
        { text: `Drawing image is ${input.imageWidth} x ${input.imageHeight} px. Question: ${input.question}` },
        { inlineData: { mimeType: image.mime, data: image.base64 } },
      ],
    },
  ];
  const body = JSON.stringify({
    systemInstruction: { parts: [{ text: INSTRUCTIONS }] },
    contents,
    generationConfig: {
      temperature: 0.2,
      maxOutputTokens: 8192,
      responseMimeType: "application/json",
      responseSchema: GEMINI_SCHEMA,
    },
  });
  try {
    let response: { status: number; text: string } | undefined;
    for (const candidate of models) {
      response = await postJson(
        `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(candidate)}:generateContent`,
        { "Content-Type": "application/json", "x-goog-api-key": backend.apiKey ?? "" },
        body,
        120_000,
      );
      if (response.status !== 503 && response.status !== 404) break;
      console.error("[stoa-vision] gemini status", response.status, candidate);
    }
    if (!response || response.status < 200 || response.status >= 300) {
      console.error("[stoa-vision] gemini status", response?.status ?? 0);
      return { ok: false, error: geminiHttpError(response?.status ?? 0, response?.text ?? "") };
    }
    const payload = JSON.parse(response.text) as {
      candidates?: { content?: { parts?: { text?: string; thought?: boolean }[] } }[];
      promptFeedback?: { blockReason?: string };
    };
    if (payload.promptFeedback?.blockReason) {
      return { ok: false, error: "The model declined to read this drawing. Try another sheet." };
    }
    const text = (payload.candidates?.[0]?.content?.parts ?? [])
      .filter((part) => part.text && !part.thought)
      .map((part) => part.text)
      .join("\n");
    return { ok: true, raw: parseAnalysisText(text) };
  } catch (error) {
    console.error("[stoa-vision] analysis failed", error instanceof Error ? error.message : error);
    const message = error instanceof Error ? error.message : "";
    if (/unreadable answer/i.test(message)) return { ok: false, error: message };
    if (/too long/i.test(message)) return { ok: false, error: message };
    return { ok: false, error: "The vision model did not answer. Try the question again." };
  }
}

function dataUrlParts(dataUrl: string): { mime: string; base64: string } | null {
  const match = /^data:([^;,]+);base64,([A-Za-z0-9+/=\s]+)$/.exec(dataUrl);
  if (!match?.[1] || !match[2]) return null;
  return { mime: match[1], base64: match[2].replace(/\s/g, "") };
}

function parseAnalysisText(text: string): RawAnalysis {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("The AI returned an unreadable answer. Try rephrasing the question.");
  let parsed: Partial<RawAnalysis>;
  try {
    parsed = JSON.parse(trimmed.slice(start, end + 1)) as Partial<RawAnalysis>;
  } catch {
    throw new Error("The AI returned an unreadable answer. Try rephrasing the question.");
  }
  const items = Array.isArray(parsed.items) ? parsed.items : [];
  return {
    answer: String(parsed.answer ?? ""),
    object_type: String(parsed.object_type ?? ""),
    count: Number(parsed.count ?? items.length),
    items: items.map((item) => ({
      label: String(item?.label ?? ""),
      ymin: Number(item?.ymin),
      xmin: Number(item?.xmin),
      ymax: Number(item?.ymax),
      xmax: Number(item?.xmax),
    })),
  };
}

function geminiHttpError(status: number, body: string): string {
  if (status === 404) return "This model is not on the free key. In .env set STOA_MODEL to a Flash model from AI Studio, then restart.";
  if (status === 401 || status === 403) return "The Gemini key was rejected. Copy it again into STOA_API_KEY and restart.";
  if (status === 429) return "The free Gemini quota is used up for the moment. Wait a minute and try again.";
  if (status === 400) return safeMessage(body) ?? "The drawing couldn't be processed. Try a smaller or clearer image.";
  const message = safeMessage(body);
  return message ? `The vision model refused the drawing: ${message}` : "The vision model had a temporary problem. Please try again.";
}

function postJson(url: string, headers: Record<string, string>, body: string, timeoutMs: number): Promise<{ status: number; text: string }> {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const req = https.request(
      {
        hostname: target.hostname,
        path: `${target.pathname}${target.search}`,
        method: "POST",
        headers: { ...headers, "Content-Length": Buffer.byteLength(body) },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, text: Buffer.concat(chunks).toString("utf8") }));
      },
    );
    const timer = setTimeout(() => {
      req.destroy(new Error("The vision model took too long to answer. Try again."));
    }, timeoutMs);
    req.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    req.on("close", () => clearTimeout(timer));
    req.end(body);
  });
}
