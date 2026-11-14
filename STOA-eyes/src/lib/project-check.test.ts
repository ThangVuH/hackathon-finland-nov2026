import { describe, expect, it } from "vitest";

import { checkProject, drawingMatchesSpace, type ProjectDocument } from "./project-check";

const schedule: ProjectDocument = {
  name: "schedule.xlsx",
  drawing: false,
  grids: [
    {
      sheet: "Openings",
      rows: [
        ["Space", "Windows", "Doors"],
        ["Office 1", "4", "2"],
        ["Kitchen", "1", "1"],
      ],
    },
  ],
};

describe("checkProject", () => {
  it("matches a schedule row to a blueprint with the same space in the file name", () => {
    const report = checkProject([
      schedule,
      { name: "A-201 Office 1.png", drawing: true },
      { name: "A-110 Kitchen plan.png", drawing: true },
    ]);
    expect(report.headline).toBe("Project files agree");
    expect(report.matches).toBe(4);
    const windows = report.findings.find((f) => f.space === "Office 1" && f.element === "window");
    expect(windows).toMatchObject({ status: "match", blueprint: "A-201 Office 1.png" });
    expect(windows?.quantities).toEqual([{ source: "schedule.xlsx · Openings", quantity: 4 }]);
  });

  it("flags a conflict when notes disagree with the schedule", () => {
    const report = checkProject([
      schedule,
      { name: "A-201 Office 1.png", drawing: true },
      { name: "site-meeting.txt", drawing: false, text: "Office 1 windows were reduced to 3. Doors stay at 2." },
    ]);
    const windows = report.findings.find((f) => f.space === "Office 1" && f.element === "window");
    expect(windows?.status).toBe("mismatch");
    expect(windows?.quantities.map((q) => q.quantity).sort()).toEqual([3, 4]);
    expect(report.headline).toBe("Conflicts in the project set");
    expect(report.summary).toContain("Office 1 windows");
  });

  it("leaves a claim unchecked when no blueprint name corresponds", () => {
    const report = checkProject([schedule, { name: "A-201 Office 1.png", drawing: true }]);
    const kitchen = report.findings.find((f) => f.space === "Kitchen" && f.element === "door");
    expect(kitchen?.status).toBe("unchecked");
    expect(kitchen?.blueprint).toBeNull();
    expect(report.headline).toBe("Blueprints missing for some claims");
  });

  it("does not pair Bedroom 2 with a Bedroom 1 sheet", () => {
    expect(drawingMatchesSpace("Bedroom 2", "A-102 Bedroom 1.png")).toBe(false);
    expect(drawingMatchesSpace("Bedroom 1", "A-102 Bedroom 1.png")).toBe(true);
    expect(drawingMatchesSpace("Office 1", "A-201 Office Level 1.png")).toBe(true);
  });

  it("reads a tall element/count table and a prose list", () => {
    const report = checkProject([
      {
        name: "doors.csv",
        drawing: false,
        grids: [
          {
            sheet: "",
            rows: [
              ["Room", "Element", "Count"],
              ["Office 1", "Door", "2"],
            ],
          },
        ],
      },
      {
        name: "spec.txt",
        drawing: false,
        text: "Office 1: 4 windows, 2 doors",
      },
      { name: "A-201 Office 1.png", drawing: true },
    ]);
    const doors = report.findings.find((f) => f.element === "door");
    expect(doors?.status).toBe("match");
    expect(doors?.quantities).toHaveLength(2);
  });
});
