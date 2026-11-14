import { createOpenAI } from "@ai-sdk/openai";
import { APICallError, NoObjectGeneratedError, Output, jsonSchema, streamText, type ModelMessage } from "ai";

import { createLovableAiGatewayRunIdFetch } from "./ai/run-id.server";
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

export async function analyzeDrawingOnServer(input: AnalyzeInput): Promise<AnalyzeOutcome> {
  const apiKey = process.env["LOVABLE_API_KEY"];
  if (!apiKey) return { ok: false, error: "The AI service isn't configured for this app." };

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
