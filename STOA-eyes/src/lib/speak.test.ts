import { describe, expect, it } from "vitest";

import { spokenAnswer } from "./speak";

describe("spoken answers", () => {
  it("turns a bare count into a sentence that names each door", () => {
    const text = spokenAnswer({
      answer: "There are 2 doors in the drawing.",
      objectType: "Door",
      count: 2,
      detections: [
        { tag: "Door #1", label: "Bedroom 1 door", box: [0, 0, 10, 10] },
        { tag: "Door #2", label: "Bath door", box: [20, 20, 30, 30] },
      ],
    });
    expect(text.startsWith("There are 2 doors on this sheet.")).toBe(true);
    expect(text).toContain("Door #1 is the Bedroom 1 door");
    expect(text).toContain("and Door #2 is the Bath door");
  });

  it("keeps a reply that is already more than a count", () => {
    const written = "Yes. Door #1 faces Door #4 across the hallway.";
    expect(spokenAnswer({ answer: written, objectType: "Door", count: 2, detections: [] })).toBe(written);
  });
});
