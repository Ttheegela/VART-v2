import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StatusPanel from "./StatusPanel";

const respond = (status: number, body: unknown) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));

/** The value cell of the row with this label. */
const row = (label: string) => screen.getByText(label).nextElementSibling;

describe("StatusPanel", () => {
  it("shows a healthy system in words", async () => {
    respond(200, { status: "ok", db: "ok", canary: { ok: true, at: "2026-10-03T06:00:00Z", credits_usd: 8 } });
    render(<StatusPanel />);
    expect(await screen.findByText("database")).toBeInTheDocument();
    expect(row("overall")).toHaveTextContent(/^OK$/);
    expect(row("database")).toHaveTextContent(/^OK$/);
    expect(row("model check")).toHaveTextContent(/^OK \(.+\)$/);
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
    expect(row("model check")).toHaveTextContent(/^Unknown$/);
  });

  it("shows a failing model check", async () => {
    respond(200, { status: "degraded", db: "ok", canary: { ok: false, at: "2026-10-03T06:00:00Z", credits_usd: null } });
    render(<StatusPanel />);
    expect(await screen.findByText("model check")).toBeInTheDocument();
    expect(row("model check")).toHaveTextContent(/^Failing$/);
    expect(row("overall")).toHaveTextContent(/^Degraded$/);
  });
});
