import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ensureWorkspace, getHealth, resetWorkspaceForTests } from "./api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("api", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("creates the workspace once", async () => {
    const fetchMock = vi.fn(async () => json(200, { created_at: "2026-10-03T12:00:00Z" }));
    vi.stubGlobal("fetch", fetchMock);
    await ensureWorkspace();
    await ensureWorkspace();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reads a degraded health body from a 503", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(503, { status: "degraded", db: "unavailable" })));
    await expect(getHealth()).resolves.toEqual({ status: "degraded", db: "unavailable" });
  });

  it("turns other failures into ApiError with the server's detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(429, { detail: "too many new sessions" })));
    await expect(ensureWorkspace()).rejects.toEqual(new ApiError(429, "too many new sessions"));
  });
});
