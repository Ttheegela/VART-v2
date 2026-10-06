import { beforeEach, describe, expect, expectTypeOf, it, vi } from "vitest";
import { ApiError, ensureWorkspace, errorMessage, getHealth, request, resetWorkspaceForTests } from "./api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("api", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("creates the workspace once", async () => {
    const fetchMock = vi.fn(async () => json(200, { created_at: "2026-10-03T12:00:00Z", expires_at: "2026-10-04T12:00:00Z" }));
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

  it("keeps Retry-After on a 429", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "budget" }), { status: 429, headers: { "Retry-After": "120" } })));
    await expect(request("/api/runs/r/step", { method: "POST" })).rejects.toMatchObject({ status: 429, retryAfter: 120 });
  });

  it("reads no body from a 204", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    const reset = request("/api/workspace/reset", { method: "POST" });
    expectTypeOf(reset).resolves.toBeVoid();
    await expect(reset).resolves.toBeUndefined();
  });

  it("turns a health page that is not JSON into a readable error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>503 Service Unavailable</html>", { status: 503 })));
    await expect(getHealth()).rejects.toEqual(new ApiError(503, "Request failed (503)"));
  });

  it("joins validation details", async () => {
    const res = json(422, { detail: [{ msg: "field required" }, { msg: "value too long" }] });
    expect(await errorMessage(res)).toBe("field required; value too long");
  });

  it("falls back to the status when the error body is not JSON", async () => {
    expect(await errorMessage(new Response("Internal Server Error", { status: 500 }))).toBe("Request failed (500)");
  });
});
