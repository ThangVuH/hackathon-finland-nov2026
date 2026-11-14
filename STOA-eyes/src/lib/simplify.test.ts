import { describe, expect, it } from "vitest";

import { nearestAspectRatio, readBananaImage } from "./simplify";

describe("Nano Banana simplify", () => {
  it("picks the aspect closest to the sheet", () => {
    expect(nearestAspectRatio(1536, 1152)).toBe("4:3");
    expect(nearestAspectRatio(800, 1400)).toBe("9:16");
  });

  it("reads the final image and skips a thought image", () => {
    const read = readBananaImage({
      candidates: [
        {
          content: {
            parts: [
              { thought: true, inlineData: { mimeType: "image/png", data: "a".repeat(40) } },
              { text: "A floor plan of one apartment." },
              { inlineData: { mimeType: "image/png", data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ" } },
            ],
          },
        },
      ],
    });
    expect(read?.note).toBe("A floor plan of one apartment.");
    expect(read?.imageDataUrl.startsWith("data:image/png;base64,iVBOR")).toBe(true);
  });

  it("returns nothing when the model sent no image", () => {
    expect(readBananaImage({ candidates: [{ content: { parts: [{ text: "no drawing" }] } }] })).toBeNull();
  });
});
