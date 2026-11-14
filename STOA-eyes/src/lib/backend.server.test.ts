import { describe, expect, it } from "vitest";

import { answerSampleSheet, selectBackend } from "./backend.server";

describe("drawing backend", () => {
  it("uses the local sample reader when no model key is set", () => {
    expect(selectBackend({}).kind).toBe("local");
  });

  it("prefers our API key over the Lovable gateway", () => {
    const backend = selectBackend({ STOA_API_KEY: "stoa", LOVABLE_API_KEY: "lovable", STOA_MODEL: "gpt-4o" });
    expect(backend).toMatchObject({ kind: "openai", model: "gpt-4o", baseURL: "https://api.openai.com/v1" });
  });

  it("counts the office sample rooms, doors, and columns", () => {
    const rooms = answerSampleSheet("A-201 · Office Level 1", "How many rooms?");
    const doors = answerSampleSheet("A-201 Office 1.jpg", "How many doors?");
    const columns = answerSampleSheet("sample office", "Count the columns");
    expect(rooms?.count).toBe(7);
    expect(doors?.count).toBe(7);
    expect(columns?.count).toBe(16);
    expect(rooms?.items).toHaveLength(7);
  });

  it("counts the apartment sample and refuses an unknown sheet", () => {
    expect(answerSampleSheet("A-101 · 2BR Apartment", "Count all windows")?.count).toBe(3);
    expect(answerSampleSheet("A-101 · 2BR Apartment", "Count the columns")?.count).toBe(0);
    expect(answerSampleSheet("random-plan.png", "How many doors?")).toBeNull();
  });
});
