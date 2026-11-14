import { describe, expect, it } from "vitest";

import { offTopicReply } from "./off-topic";

describe("off topic questions", () => {
  it("sends a greeting back to the drawing work", () => {
    const reply = offTopicReply("Bonsoir");
    expect(reply).toContain("Let's get back to work");
    expect(reply).toContain("doors, windows, rooms, and columns");
    expect(reply).not.toContain("Door #");
  });

  it("keeps count questions and follow-ups on the drawing", () => {
    expect(offTopicReply("How many doors?")).toBeNull();
    expect(offTopicReply("door 1 is opposite the 4th door?")).toBeNull();
    expect(offTopicReply("Count the columns")).toBeNull();
  });

  it("keeps a summary of a named blueprint on the drawing", () => {
    expect(offTopicReply("Summarize the object's information in blue print 2002")).toBeNull();
    expect(offTopicReply("Describe what is on sheet 2002")).toBeNull();
  });

  it("treats summarize this image as a summary of the open sheet", () => {
    expect(offTopicReply("summarize this image")).toBeNull();
    expect(offTopicReply("Summarize the picture")).toBeNull();
    expect(offTopicReply("hello")).toContain("Let's get back to work");
  });
});
