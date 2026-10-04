import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StatusPanel from "./StatusPanel";

const respond = (status: number, body: unknown) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));

describe("StatusPanel", () => {
  it("shows a healthy system in words", async () => {
    respond(200, { status: "ok", db: "ok", canary: { ok: true, at: "2026-10-03T06:00:00Z", credits_usd: 8 } });
    render(<StatusPanel />);
    expect(await screen.findByText("Database")).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(2);
  });

  it("says when the model check has not run", async () => {
    respond(200, { status: "ok", db: "ok", canary: null });
    render(<StatusPanel />);
    expect(await screen.findByText("Not run yet")).toBeInTheDocument();
  });

  it("shows an unavailable database", async () => {
    respond(503, { status: "degraded", db: "unavailable" });
    render(<StatusPanel />);
    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });
});
