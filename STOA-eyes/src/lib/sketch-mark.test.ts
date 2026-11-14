import { describe, expect, it } from "vitest";

import { classifyInk } from "./sketch-mark";

function sheet(width: number, height: number, fill: number): Uint8Array {
  return new Uint8Array(width * height).fill(fill);
}

describe("sheet marks", () => {
  it("marks a clean black-on-white sheet as drafted only", () => {
    const gray = sheet(80, 40, 255);
    for (let x = 4; x < 76; x++) gray[20 * 80 + x] = 0;
    expect(classifyInk(gray, 80, 40)).toEqual({ drafted: true, handSketch: false, complicated: false });
  });

  it("marks gray paper and uneven pencil as a sketch only", () => {
    const gray = sheet(80, 40, 188);
    for (let y = 8; y < 32; y++) {
      for (let x = 6; x < 70; x++) {
        const wobble = (x * 17 + y * 13) % 5;
        gray[y * 80 + x] = 30 + wobble * 28;
      }
    }
    expect(classifyInk(gray, 80, 40)).toEqual({ drafted: false, handSketch: true, complicated: true });
  });

  it("keeps both marks when pencil sits on a drafted sheet", () => {
    const gray = sheet(80, 40, 255);
    for (let x = 4; x < 76; x++) gray[20 * 80 + x] = 0;
    for (let y = 2; y < 8; y++) {
      for (let x = 8; x < 50; x++) gray[y * 80 + x] = 60 + ((x + y) % 4) * 24;
    }
    expect(classifyInk(gray, 80, 40)).toEqual({ drafted: true, handSketch: true, complicated: true });
  });
});
