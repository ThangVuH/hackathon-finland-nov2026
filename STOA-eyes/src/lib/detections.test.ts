import { describe, expect, it } from "vitest";
import { normalizeAnalysis, stabilizeDetections, type Detection } from "./detections";

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

  it("numbers each kind on its own and reads the kind from the item", () => {
    const r = normalizeAnalysis({
      answer: "Doors, windows, and rooms.",
      object_type: "object",
      count: 3,
      items: [
        { kind: "Window", label: "Living window", ymin: 10, xmin: 10, ymax: 40, xmax: 80 },
        { kind: "Door", label: "Bedroom 1 door", ymin: 100, xmin: 100, ymax: 160, xmax: 140 },
        { kind: "Room", label: "Kitchen", ymin: 200, xmin: 200, ymax: 500, xmax: 600 },
      ],
    });
    expect(r.detections.map((item) => item.tag)).toEqual(["Window #1", "Door #1", "Room #1"]);
    expect(r.objectType).toBe("Object");
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

describe("stabilizeDetections", () => {
  const bedroom: Detection = { tag: "Door #1", label: "Bedroom 1 door", box: [400, 420, 520, 500] };
  const bath: Detection = { tag: "Door #2", label: "Bath door", box: [600, 640, 700, 730] };

  it("keeps Bedroom 1 door as #1 when a later answer lists it second", () => {
    const again = normalizeAnalysis({
      answer: "There are 2 doors.",
      object_type: "door",
      count: 2,
      items: [
        { label: "Bath door", ymin: 605, xmin: 645, ymax: 705, xmax: 735 },
        { label: "Bedroom 1 door", ymin: 410, xmin: 430, ymax: 530, xmax: 510 },
      ],
    });
    const stable = stabilizeDetections([bedroom, bath], again);
    expect(stable.detections.map((item) => `${item.tag} ${item.label}`)).toEqual([
      "Door #1 Bedroom 1 door",
      "Door #2 Bath door",
    ]);
  });

  it("does not give a new door a number already used by a door that is missing this time", () => {
    const again = normalizeAnalysis({
      answer: "There is 1 door.",
      object_type: "door",
      count: 1,
      items: [{ label: "Entrance door", ymin: 800, xmin: 100, ymax: 900, xmax: 200 }],
    });
    const stable = stabilizeDetections([bedroom], again);
    expect(stable.detections[0]!.tag).toBe("Door #2");
  });

  it("leaves a window number alone when matching doors", () => {
    const window: Detection = { tag: "Window #1", label: "Bedroom 1 window", box: [100, 100, 140, 200] };
    const again = normalizeAnalysis({
      answer: "There is 1 door.",
      object_type: "door",
      count: 1,
      items: [{ label: "Bedroom 1 door", ymin: 400, xmin: 420, ymax: 520, xmax: 500 }],
    });
    expect(stabilizeDetections([window], again).detections[0]!.tag).toBe("Door #1");
  });
});
