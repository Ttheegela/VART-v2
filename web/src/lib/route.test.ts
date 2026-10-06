import { describe, expect, it } from "vitest";
import { href, readRoute } from "./route";

describe("route", () => {
  it("reads and writes the query string only", () => {
    expect(readRoute("?view=run&run=r1&item=i9")).toEqual({ view: "run", run: "r1", item: "i9" });
    expect(href({ view: "run", run: "r1" })).toBe("?view=run&run=r1");
  });

  it("falls back to home for an unknown view", () => {
    expect(readRoute("?view=../../etc")).toEqual({ view: "home" });
    expect(readRoute("")).toEqual({ view: "home" });
  });
});
