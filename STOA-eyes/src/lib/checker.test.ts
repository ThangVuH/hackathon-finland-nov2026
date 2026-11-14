import { describe, expect, it } from "vitest";
import { arbitrate, nameReason, questionType, withoutDetector, type CheckerItem, type VisionPayload } from "./checker";

function box(kind: string, xmin: number, ymin: number, xmax: number, ymax: number, score = 0.9): CheckerItem {
  return { kind, label: kind, xmin, ymin, xmax, ymax, score };
}

describe("questionType", () => {
  it("recognises windows, doors, both, and everything else", () => {
    expect(questionType("How many windows?")).toBe("window");
    expect(questionType("Combien de portes ?")).toBe("door");
    expect(questionType("Count the doors and the windows")).toBe("both");
    expect(questionType("How many rooms?")).toBe("other");
    expect(questionType("Count the doorways without a leaf")).toBe("other");
  });
});

describe("nameReason", () => {
  it("refuses IFC, PDF, archive sheets, and archive sources", () => {
    expect(nameReason("block.ifc")).toContain("IFC");
    expect(nameReason("level.pdf")).toContain("PDF");
    expect(nameReason("al1276_sheet_00001.jpg")?.toLowerCase()).toContain("sheet");
    expect(nameReason("data/habs/plan.jpg")).toContain("Archive");
    expect(nameReason("high_quality-11459.png")).toBeNull();
    expect(nameReason("high_quality_architectural-10491.png")).toBeNull();
    expect(nameReason("data/finna/scan.jpg")).toBeTruthy();
  });
});

describe("arbitrate", () => {
  it("marks overlapping equal totals reliable", () => {
    const vision: VisionPayload = { available: true, object_type: "Window", items: [box("window", 12, 12, 42, 42)], answer: "1" };
    const result = arbitrate("window", [box("window", 10, 10, 40, 40)], 0.8, vision);
    expect(result.verdict).toBe("reliable");
    expect(result.count).toBe(1);
    expect(result.items[0]?.disputed).toBe(false);
    expect(result.items[0]?.source).toBe("both");
  });

  it("sends the same total in a different place to review", () => {
    const vision: VisionPayload = { available: true, object_type: "Window", items: [box("window", 700, 700, 900, 900)] };
    const result = arbitrate("window", [box("window", 10, 10, 40, 40)], 0.8, vision);
    expect(result.verdict).toBe("review");
    expect(result.count).toBe(1);
    expect(result.items[0]?.disputed).toBe(true);
    const extras = result.items.filter((item) => item.source === "vision");
    expect(extras).toHaveLength(1);
    expect(extras[0]?.included).toBe(false);
  });

  it("highlights the extra box when the totals differ", () => {
    const vision: VisionPayload = { available: true, object_type: "Door", items: [box("door", 10, 10, 40, 40)] };
    const result = arbitrate("door", [box("door", 10, 10, 40, 40), box("door", 100, 100, 140, 140, 0.4)], 0.7, vision);
    expect(result.verdict).toBe("review");
    expect(result.count).toBe(2);
    expect(result.items.filter((item) => item.disputed)).toHaveLength(1);
  });

  it("does not call a detector-only count reliable", () => {
    const result = arbitrate("window", [box("window", 10, 10, 40, 40)], 0.6, null);
    expect(result.verdict).toBe("review");
    expect(result.answer).toContain("did not confirm");
  });

  it("trusts two empty counts", () => {
    const result = arbitrate("door", [], 1, { available: true, object_type: "Door", items: [] });
    expect(result.verdict).toBe("reliable");
    expect(result.count).toBe(0);
  });

  it("leaves other questions to the vision model", () => {
    const vision: VisionPayload = {
      available: true,
      object_type: "Room",
      answer: "There are 3 rooms.",
      count: 1,
      items: [box("Room", 0, 0, 100, 100)],
    };
    const result = arbitrate("other", [], 0, vision);
    expect(result.verdict).toBe("unverified");
    expect(result.warning).toContain("vision model alone");
  });
});

describe("withoutDetector", () => {
  it("still answers a window question and marks it unchecked", () => {
    const vision: VisionPayload = {
      available: true,
      object_type: "Window",
      answer: "There are 2 windows.",
      count: 2,
      items: [box("Window", 0, 0, 10, 10), box("Window", 20, 20, 40, 40)],
    };
    const result = withoutDetector("window", vision);
    expect(result.verdict).toBe("unverified");
    expect(result.count).toBe(2);
    expect(result.warning).toContain("not running");
    expect(result.answer).not.toContain("The detector counts 0");
  });
});
