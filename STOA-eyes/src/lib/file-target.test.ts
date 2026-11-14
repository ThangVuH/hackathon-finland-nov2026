import { describe, expect, it } from "vitest";

import { selectDrawingTargets } from "./file-target";

const files = [
  { id: "a", name: "plan-1732.png" },
  { id: "b", name: "office-4401.jpg" },
  { id: "c", name: "sample-apartment.webp" },
];

describe("selectDrawingTargets", () => {
  it("reads blueprint 2002 when the question says blue print 2002", () => {
    const sheets = [
      { id: "a", name: "plan-2002.png" },
      { id: "b", name: "office-4401.jpg" },
    ];
    const picked = selectDrawingTargets("Summarize the object's information in blue print 2002", sheets, "b");
    expect(picked).toEqual({ kind: "files", files: [sheets[0]] });
  });

  it("reads only the file whose name contains the number in the question", () => {
    const picked = selectDrawingTargets("How many doors in 1732?", files, "b");
    expect(picked).toEqual({ kind: "files", files: [files[0]] });
  });

  it("matches a word in the file name", () => {
    const picked = selectDrawingTargets("Count the windows on the apartment sheet", files, "a");
    expect(picked).toEqual({ kind: "files", files: [files[2]] });
  });

  it("does not read the other files when the cited number is missing", () => {
    const picked = selectDrawingTargets("How many doors in 9999?", files, "a");
    expect(picked.kind).toBe("missing");
    if (picked.kind === "missing") {
      expect(picked.reply).toContain("9999");
      expect(picked.reply).toContain("plan-1732.png");
      expect(picked.reply).not.toContain("analyz");
    }
  });

  it("asks which drawing when a general question has several files", () => {
    const picked = selectDrawingTargets("How many doors?", files, "b");
    expect(picked).toEqual({ kind: "choose", files });
  });

  it("reads the only drawing when the question names no file", () => {
    const only = [files[1]!];
    const picked = selectDrawingTargets("How many doors?", only, "b");
    expect(picked).toEqual({ kind: "files", files: only });
  });

  it("reads every drawing only when the question asks for all of them", () => {
    const picked = selectDrawingTargets("How many doors on every drawing?", files, "a");
    expect(picked).toEqual({ kind: "files", files });
  });

  it("asks which drawing for a follow-up that names no file", () => {
    const picked = selectDrawingTargets("door 1 is opposite the 4th door?", files, "c");
    expect(picked).toEqual({ kind: "choose", files });
  });
});
