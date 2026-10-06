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

it("the gap view keeps its scope and outcome in the query string", () => {
  const r = readRoute("?view=gap&scope=protect&item=PR.DS-11");
  expect(r).toEqual({ view: "gap", scope: "protect", item: "PR.DS-11" });
  expect(href(r)).toBe("?view=gap&item=PR.DS-11&scope=protect");
});
