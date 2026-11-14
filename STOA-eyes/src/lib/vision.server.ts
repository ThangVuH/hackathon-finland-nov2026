import https from "node:https";

import { createOpenAI } from "@ai-sdk/openai";
import { APICallError, NoObjectGeneratedError, Output, jsonSchema, streamText, type ModelMessage } from "ai";

import { createLovableAiGatewayRunIdFetch } from "./ai/run-id.server";
import { answerSampleSheet, localMissError, selectBackend, type BackendInfo } from "./backend.server";
import type { RawAnalysis } from "./detections";
import { instructionsFor } from "./drawing-prompts";
import { nearestAspectRatio, readBananaImage, SIMPLIFY_PROMPT } from "./simplify";

const GATEWAY_URL = "https://ai.gateway.lovable.dev/v1";
const MODEL = "openai/gpt-6-astra";

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
  sheetName?: string;
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

export async function analyzeDrawingOnServer(input: AnalyzeInput): Promise<AnalyzeOutcome> {
  const backend = selectBackend(process.env);
  if (backend.kind === "local") {
    const raw = answerSampleSheet(input.sheetName, input.question);
    return raw ? { ok: true, raw } : { ok: false, error: localMissError() };
  }
  if (backend.kind === "openai") return analyzeWithChatModel(input, backend);

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
      instructions: instructionsFor(input.question),
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

async function analyzeWithChatModel(input: AnalyzeInput, backend: BackendInfo): Promise<AnalyzeOutcome> {
  if ((backend.baseURL ?? "").includes("generativelanguage.googleapis.com")) {
    return analyzeWithGemini(input, backend);
  }
  const provider = createOpenAI({ baseURL: backend.baseURL, apiKey: backend.apiKey });
  const messages: ModelMessage[] = [
    ...input.history.slice(-8).map(
      (m): ModelMessage =>
        m.role === "user" ? { role: "user", content: m.text } : { role: "assistant", content: m.text },
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
      instructions: instructionsFor(input.question),
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

export interface SimplifyInput {
  imageDataUrl: string;
  imageWidth: number;
  imageHeight: number;
}

export type SimplifyOutcome = { ok: true; imageDataUrl: string; note: string } | { ok: false; error: string };

const BANANA_FALLBACKS = ["gemini-3.1-flash-lite-image", "gemini-2.5-flash-image", "gemini-3.1-flash-image"];
let bananaBlocked: string | null = null;

export async function simplifyDrawingOnServer(input: SimplifyInput): Promise<SimplifyOutcome> {
  const key = googleImageKey(process.env);
  if (!key) {
    return { ok: false, error: "Nano Banana needs the Gemini key in STOA_API_KEY. This sheet is used as drawn." };
  }
  if (bananaBlocked) return { ok: false, error: bananaBlocked };
  const image = dataUrlParts(input.imageDataUrl);
  if (!image) return { ok: false, error: "The drawing couldn't be prepared. This sheet is used as drawn." };
  const configured = process.env.STOA_IMAGE_MODEL?.trim();
  const models = configured ? [configured] : [];
  for (const fallback of BANANA_FALLBACKS) {
    if (!models.includes(fallback)) models.push(fallback);
  }
  const withAspect = bananaBody(image, nearestAspectRatio(input.imageWidth, input.imageHeight));
  const imageOnly = bananaBody(image, null);
  try {
    let response: { status: number; text: string } | undefined;
    for (const candidate of models) {
      let modelMissing = false;
      for (const payload of [withAspect, imageOnly]) {
        response = await postJson(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(candidate)}:generateContent`,
          { "Content-Type": "application/json", "x-goog-api-key": key },
          payload,
          90_000,
          "Nano Banana took too long. This sheet is used as drawn.",
        );
        if (response.status >= 200 && response.status < 300) {
          try {
            const read = readBananaImage(JSON.parse(response.text) as unknown);
            if (read) return { ok: true, imageDataUrl: read.imageDataUrl, note: read.note };
          } catch {
            console.error("[stoa-vision] banana returned no image", candidate);
          }
          continue;
        }
        console.error("[stoa-vision] banana status", response.status, candidate, safeMessage(response.text) ?? "");
        if (response.status === 404 || response.status === 503 || response.status === 429) {
          modelMissing = true;
          break;
        }
        if (response.status !== 400) return { ok: false, error: bananaHttpError(response.status, response.text) };
      }
      if (!modelMissing && response && response.status !== 400 && (response.status < 200 || response.status >= 300)) break;
    }
    const error = bananaHttpError(response?.status ?? 0, response?.text ?? "");
    if ((response?.status ?? 0) === 429) bananaBlocked = error;
    return { ok: false, error };
  } catch (error) {
    console.error("[stoa-vision] banana failed", error instanceof Error ? error.message : error);
    const message = error instanceof Error ? error.message : "";
    if (/too long/i.test(message)) return { ok: false, error: message };
    return { ok: false, error: "Nano Banana did not redraw this sheet. It is used as drawn." };
  }
}

function googleImageKey(env: Record<string, string | undefined>): string | null {
  const key = env.STOA_API_KEY?.trim();
  if (!key) return null;
  const base = env.STOA_API_BASE ?? "";
  if (base && !base.includes("generativelanguage.googleapis.com")) return null;
  return key;
}

function bananaBody(image: { mime: string; base64: string }, aspectRatio: string | null): string {
  const generationConfig: Record<string, unknown> = {
    responseModalities: aspectRatio ? ["TEXT", "IMAGE"] : ["IMAGE"],
  };
  if (aspectRatio) generationConfig.imageConfig = { aspectRatio };
  return JSON.stringify({
    contents: [
      {
        role: "user",
        parts: [{ text: SIMPLIFY_PROMPT }, { inlineData: { mimeType: image.mime, data: image.base64 } }],
      },
    ],
    generationConfig,
  });
}

function bananaHttpError(status: number, body: string): string {
  if (status === 404) return "Nano Banana is not on this key. This sheet is used as drawn.";
  if (status === 401 || status === 403) return "The Gemini key was rejected. This sheet is used as drawn.";
  if (status === 429) {
    const message = safeMessage(body) ?? "";
    if (/limit:\s*0/.test(message)) return "Nano Banana is not included on this free key. This sheet is used as drawn.";
    return "The free Gemini quota is used up for the moment. This sheet is used as drawn.";
  }
  if (status === 400) return safeMessage(body) ?? "Nano Banana could not redraw this sheet. It is used as drawn.";
  return "Nano Banana did not redraw this sheet. It is used as drawn.";
}

const textCooldown = new Map<string, number>();

function modelCooling(model: string): boolean {
  return (textCooldown.get(model) ?? 0) > Date.now();
}

function holdModel(model: string, body: string) {
  textCooldown.set(model, Date.now() + retryDelayMs(body));
}

function retryDelayMs(body: string): number {
  const message = `${safeMessage(body) ?? ""} ${body}`;
  const match = /retry in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?/i.exec(message);
  if (!match || (!match[1] && !match[2] && !match[3])) return 60_000;
  const ms = (Number(match[1] ?? 0) * 3600 + Number(match[2] ?? 0) * 60 + Number(match[3] ?? 0)) * 1000;
  return Math.min(Math.max(ms, 5_000), 24 * 60 * 60 * 1000);
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
  for (const fallback of ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash"]) {
    if (!models.includes(fallback)) models.push(fallback);
  }
  const usable = models.filter((candidate) => !modelCooling(candidate));
  if (usable.length === 0) {
    return { ok: false, error: "The free Gemini quota is used up for the moment. Wait a minute and try again." };
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
    systemInstruction: { parts: [{ text: instructionsFor(input.question) }] },
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
    for (const candidate of usable) {
      try {
        response = await postJsonRetry(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(candidate)}:generateContent`,
          { "Content-Type": "application/json", "x-goog-api-key": backend.apiKey ?? "" },
          body,
          120_000,
        );
      } catch (error) {
        console.error("[stoa-vision] gemini request", candidate, error instanceof Error ? error.message : error);
        response = undefined;
        continue;
      }
      if (response.status === 429) {
        holdModel(candidate, response.text);
        console.error("[stoa-vision] gemini status", response.status, candidate, safeMessage(response.text) ?? "");
        continue;
      }
      if (response.status === 503 || response.status === 404) {
        console.error("[stoa-vision] gemini status", response.status, candidate);
        continue;
      }
      if (response.status < 200 || response.status >= 300) break;
      let payload: {
        candidates?: { content?: { parts?: { text?: string; thought?: boolean }[] } }[];
        promptFeedback?: { blockReason?: string };
      };
      try {
        payload = JSON.parse(response.text) as typeof payload;
      } catch {
        console.error("[stoa-vision] gemini unreadable", candidate);
        continue;
      }
      if (payload.promptFeedback?.blockReason) {
        return { ok: false, error: "The model declined to read this drawing. Try another sheet." };
      }
      const text = (payload.candidates?.[0]?.content?.parts ?? [])
        .filter((part) => part.text && !part.thought)
        .map((part) => part.text)
        .join("\n");
      try {
        return { ok: true, raw: parseAnalysisText(text) };
      } catch (error) {
        console.error("[stoa-vision] gemini unreadable", candidate, error instanceof Error ? error.message : error);
      }
    }
    if (!response || response.status < 200 || response.status >= 300) {
      console.error("[stoa-vision] gemini status", response?.status ?? 0);
      return { ok: false, error: geminiHttpError(response?.status ?? 0, response?.text ?? "") };
    }
    return { ok: false, error: "The vision model did not answer. Try the question again." };
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
  if (!match) return null;
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

async function postJsonRetry(
  url: string,
  headers: Record<string, string>,
  body: string,
  timeoutMs: number,
): Promise<{ status: number; text: string }> {
  let last: unknown;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await postJson(url, headers, body, timeoutMs);
    } catch (error) {
      last = error;
      const message = error instanceof Error ? error.message : "";
      if (!/ENOTFOUND|EAI_AGAIN|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EHOSTUNREACH|ENETUNREACH|socket/i.test(message)) throw error;
      await new Promise((resolve) => setTimeout(resolve, 700 * (attempt + 1)));
    }
  }
  throw last;
}

function postJson(
  url: string,
  headers: Record<string, string>,
  body: string,
  timeoutMs: number,
  timeoutMessage = "The vision model took too long to answer. Try again.",
): Promise<{ status: number; text: string }> {
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
      req.destroy(new Error(timeoutMessage));
    }, timeoutMs);
    req.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    req.on("close", () => clearTimeout(timer));
    req.end(body);
  });
}
