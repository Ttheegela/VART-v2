import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { resetWorkspaceForTests } from "./lib/api";

describe("App", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("shows the product name and the system status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        new Response(
          JSON.stringify(url.endsWith("/api/workspace") ? { created_at: "2026-10-03T12:00:00Z" } : { status: "ok", db: "ok", canary: null }),
          { status: 200 },
        ),
      ),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "VART" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "System status" })).toBeInTheDocument();
  });

  it("explains when the demo cannot start", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "the demo is full right now" }), { status: 503 })));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("the demo is full right now");
  });

  it("still shows the system status when the demo cannot start", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/api/workspace")
          ? new Response("Internal Server Error", { status: 500 })
          : new Response(JSON.stringify({ status: "degraded", db: "unavailable" }), { status: 503 }),
      ),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't start the demo: Request failed (500)");
    expect((await screen.findByText("Database")).nextElementSibling).toHaveTextContent(/^Unavailable$/);
  });

  it("asks for the workspace before the health check", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      new Response(
        JSON.stringify(url.endsWith("/api/workspace") ? { created_at: "2026-10-03T12:00:00Z" } : { status: "ok", db: "ok", canary: null }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("region", { name: "System status" })).toBeInTheDocument();
    expect(await screen.findByText(/arrives in the next build/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/workspace", "/api/health"]);
  });

  it("announces both loading states", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<App />);
    expect(screen.getAllByRole("status").map((s) => s.textContent)).toEqual(["Loading…", "Checking status…"]);
  });
});
