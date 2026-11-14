import { describe, expect, it } from "vitest";
import { normalizeAnalysis } from "./detections";

const base = { answer: "There are 2 doors.", object_type: "door", count: 2 };

describe("normalizeAnalysis", () => {
  it("numbers detections as '<Type> #n'", () => {
    const r = normalizeAnalysis({
      ...base,
      items: [
        { label: "Entry", ymin: 10, xmin: 10, ymax: 50, xmax: 50 },
        { label: "Bath", ymin: 100, xmin: 100, ymax: 200, xmax: 200 },
      ],
    });
    expect(r.detections.map((d) => d.tag)).toEqual(["Door #1", "Door #2"]);
  });

  it("clamps coordinates to the 0-1000 scale", () => {
    const r = normalizeAnalysis({ ...base, items: [{ label: "", ymin: -20, xmin: 5, ymax: 1200, xmax: 990 }] });
    expect(r.detections[0]!.box).toEqual([0, 5, 1000, 990]);
  });

  it("swaps inverted corners into [ymin, xmin, ymax, xmax] order", () => {
    const r = normalizeAnalysis({ ...base, items: [{ label: "", ymin: 400, xmin: 300, ymax: 200, xmax: 100 }] });
    expect(r.detections[0]!.box).toEqual([200, 100, 400, 300]);
  });

  it("counts the boxes drawn, not the model's stated number", () => {
    const r = normalizeAnalysis({
      ...base,
      count: 5,
      items: [{ label: "", ymin: 0, xmin: 0, ymax: 10, xmax: 10 }],
    });
    expect(r.count).toBe(1);
  });
});
