import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "./App";
import { resetWorkspaceForTests } from "./lib/api";
import { fixtures, mockApi } from "./test/mockApi";

describe("App", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("asks for the workspace before any view", async () => {
    window.history.replaceState(null, "", "?view=audit");
    const calls = mockApi({ "GET /api/workspace": fixtures.workspace, "GET /api/audit": [] });
    render(<App />);
    await waitFor(() => expect(calls[0]).toBe("GET /api/workspace"));
  });

  it("a deep link shows a loading line, not Home, while the workspace loads", async () => {
    window.history.replaceState(null, "", "?view=audit");
    let open: (r: Response) => void = () => {};
    mockApi({
      "GET /api/workspace": () => new Promise<Response>((resolve) => { open = resolve; }),
      "GET /api/audit": [],
    });
    render(<App />);
    expect(await screen.findByRole("status")).toHaveTextContent("Opening your workspace…");
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    open(new Response(JSON.stringify(fixtures.workspace), { status: 200 }));
    await waitFor(() => expect(screen.queryByText("Opening your workspace…")).toBeNull());
  });

  it("opens on Home with both ways in and the system status", async () => {
    window.history.replaceState(null, "", "/");
    mockApi({ "GET /api/workspace": fixtures.workspace, "GET /api/health": fixtures.health });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: /answered from your own documents/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try with a sample company" })).toHaveAttribute("aria-keyshortcuts", "s");
    expect(await screen.findByRole("region", { name: "system status" })).toBeInTheDocument();
  });

  it("explains when the demo cannot start", async () => {
    window.history.replaceState(null, "", "/");
    mockApi({
      "GET /api/workspace": new Response(JSON.stringify({ detail: "the demo is full right now" }), { status: 503 }),
      "GET /api/health": fixtures.health,
    });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: the demo is full right now");
  });
});
