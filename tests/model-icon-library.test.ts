import { describe, expect, it } from "vitest";

import { MODEL_ICON_ASSETS, getModelIconPath, getProviderIconPath } from "../app/model-icon-library";

describe("model icon library", () => {
  it("keeps a local curated icon inventory", () => {
    const paths = Object.values(MODEL_ICON_ASSETS);
    expect(paths).toHaveLength(49);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths.every((path) => path.startsWith("/model-icons/") && path.endsWith(".svg"))).toBe(true);
  });

  it("resolves fixed relay models and common family aliases", () => {
    expect(getModelIconPath("image2.0")).toBe("/model-icons/openai.svg");
    expect(getModelIconPath("doubao-seedream-5.0-pro")).toBe("/model-icons/doubao.svg");
    expect(getModelIconPath("doubao-seed-audio-1.0")).toBe("/model-icons/doubao.svg");
    expect(getModelIconPath("wan3.0-video")).toBe("/model-icons/bailian.svg");
    expect(getModelIconPath("veo-4")).toBe("/model-icons/gemini.svg");
    expect(getModelIconPath("llama-5")).toBe("/model-icons/meta.svg");
  });

  it("falls back to a known provider without guessing unknown brands", () => {
    expect(getModelIconPath("custom-image-model", "openai")).toBe("/model-icons/openai.svg");
    expect(getProviderIconPath("volcengine_ark")).toBe("/model-icons/volcengine.svg");
    expect(getModelIconPath("unknown-model", "unknown-provider")).toBeUndefined();
  });
});
