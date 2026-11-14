import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const inputSchema = z.object({
  imageDataUrl: z.string().startsWith("data:image/").max(12_000_000),
  imageWidth: z.number().int().positive(),
  imageHeight: z.number().int().positive(),
  question: z.string().trim().min(1).max(1000),
  history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), text: z.string().max(4000) }))
    .max(20),
});

export const analyzeDrawing = createServerFn({ method: "POST" })
  .inputValidator((data: unknown) => inputSchema.parse(data))
  .handler(async ({ data }) => {
    const { analyzeDrawingOnServer } = await import("./vision.server");
    return analyzeDrawingOnServer(data);
  });
