import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { GENERATED_DIR, generate } from "../../scripts/gen-types";
import { extensions } from "../extensions";

describe("generated files", () => {
  it("match a fresh run of gen-types (no drift)", async () => {
    const fresh = await generate();
    for (const [name, text] of Object.entries(fresh)) {
      expect(readFileSync(join(GENERATED_DIR, name), "utf8"), `${name} drifted: npm run gen:types`).toBe(text);
    }
  });
});

describe("extensions", () => {
  it("are the committed schema documents, verbatim", () => {
    const compare = JSON.parse(readFileSync(join(GENERATED_DIR, "../../../../schemas/extensions/compare.json"), "utf8"));
    expect(extensions.compare).toEqual(compare);
    expect(extensions.compare.scope).toBe("intent");
    expect(extensions.rasterStyling.scope).toBe("layer");
    expect(extensions.chart.keys).toContain("chart:layer");
    expect(extensions.compare.required).toEqual(["compare:layers"]);
  });
});
