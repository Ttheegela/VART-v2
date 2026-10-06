import { render, waitFor } from "@testing-library/react";
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
});
