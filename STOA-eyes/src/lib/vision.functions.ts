import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const inputSchema = z.object({
  imageDataUrl: z.string().startsWith("data:image/").max(12_000_000),
  imageWidth: z.number().int().positive(),
  imageHeight: z.number().int().positive(),
  question: z.string().trim().min(1).max(1000),
  sheetName: z.string().trim().max(180).optional(),
  history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), text: z.string().max(4000) }))
    .max(20),
});

export const backendStatus = createServerFn({ method: "GET" }).handler(async () => {
  const { currentBackend } = await import("./vision.server");
  const backend = currentBackend();
  return { kind: backend.kind, label: backend.label };
});

export const analyzeDrawing = createServerFn({ method: "POST" })
  .inputValidator((data: unknown) => inputSchema.parse(data))
  .handler(async ({ data }) => {
    const { analyzeDrawingOnServer } = await import("./vision.server");
    return analyzeDrawingOnServer(data);
  });
