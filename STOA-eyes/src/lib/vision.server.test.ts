import { describe, expect, it } from "vitest";

import { MODEL_BUSY_REPLY, modelIsBusy } from "./vision.server";

const DEMAND =
  '{"error":{"code":503,"message":"This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.","status":"UNAVAILABLE"}}';

describe("model demand spikes", () => {
  it("treats the high-demand reply as a temporary busy model", () => {
    expect(modelIsBusy(503, DEMAND)).toBe(true);
    expect(modelIsBusy(500, DEMAND)).toBe(true);
    expect(MODEL_BUSY_REPLY).not.toMatch(/refused/i);
  });

  it("leaves a real rejection alone", () => {
    expect(modelIsBusy(400, '{"error":{"message":"Request contains an invalid argument."}}')).toBe(false);
    expect(modelIsBusy(404, '{"error":{"message":"models/gemini-2.0-flash is not found"}}')).toBe(false);
  });
});
