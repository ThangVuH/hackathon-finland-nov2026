import { describe, expect, it } from "vitest";

import { instructionsFor, promptCount } from "./drawing-prompts";

describe("drawing prompts", () => {
  it("keeps only the count and box prompts", () => {
    expect(promptCount).toBe(6);
  });

  it("tells Gemini how to count doors and where to draw the boxes", () => {
    const text = instructionsFor("How many doors?");
    expect(text).toContain("two leaves and stays one door");
    expect(text).toContain("Two swings next to each other are two doors");
    expect(text).toContain("Bedroom 1 door");
    expect(text).toContain("Dashed lines are hidden edges");
    expect(text).not.toContain("rough opening");
    expect(text).toContain("0-1000");
    expect(text).toContain("quarter-circle swing");
    expect(text).toContain("one glass wall");
    expect(text).toContain("does not split one room");
    expect(text).not.toContain("3/A-502");
    expect(text).not.toContain("Written dimensions govern");
    expect(text).not.toContain("Do not invent ducts");
    expect(text).toContain("plain sentences");
    expect(text).not.toContain("start \"answer\" with Yes or No");
  });

  it("summarizes the objects on a named blueprint in plain sentences", () => {
    const text = instructionsFor("summarize this image");
    expect(text).toContain("every object on the sheet");
    expect(text).not.toContain("start with Yes or No");
  });

  it("uses the same object summary when the sheet is named", () => {
    const text = instructionsFor("Summarize the object's information in blue print 2002");
    expect(text).toContain("every object on the sheet");
    expect(text).toContain("doors, windows, rooms, columns, and stairs");
    expect(text).toContain("window box is only the opening");
    expect(text).not.toContain("start with Yes or No");
  });

  it("tells a follow-up to answer yes or no about the numbered doors", () => {
    const text = instructionsFor("door 1 is opposite the 4th door?");
    expect(text).toContain("start with Yes or No");
    expect(text).toContain("Door #1 is the first door");
    expect(text).toContain("Door #4 is the fourth");
    expect(text).toContain("Do not reply with a new total");
  });
});