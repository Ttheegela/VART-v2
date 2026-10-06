import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { resetWorkspaceForTests } from "../lib/api";
import { fixtures, mockApi } from "../test/mockApi";
import Home, { NOTICE_URL } from "./Home";

describe("Home", () => {
  beforeEach(() => {
    resetWorkspaceForTests();
    window.history.replaceState(null, "", "/");
  });

  it("s loads the sample, starts a run and opens the run view", async () => {
    const calls = mockApi({
      "GET /api/workspace": fixtures.workspace,
      "GET /api/health": fixtures.health,
      "POST /api/documents/sample": fixtures.documents,
      "POST /api/questionnaires/sample/vsq-a": { ...fixtures.questionnaire, id: "q1", item_count: 64 },
      "POST /api/questionnaires/q1/runs": { ...fixtures.run, status: "running", done: 0 },
    });
    render(<Home workspace={fixtures.workspace} startError={null} />);
    await userEvent.keyboard("s");
    await waitFor(() => expect(window.location.search).toBe("?view=run&run=r1"));
    expect(calls).toEqual([
      "GET /api/health", "GET /api/workspace", "POST /api/documents/sample",
      "POST /api/questionnaires/sample/vsq-a", "POST /api/questionnaires/q1/runs",
    ]);
  });

  it("links the data licence notice", () => {
    mockApi({ "GET /api/health": fixtures.health });
    render(<Home workspace={fixtures.workspace} startError={null} />);
    expect(screen.getByRole("link", { name: /NOTICE/ })).toHaveAttribute("href", NOTICE_URL);
  });

  it("says the workspace is opening while it loads, and the ways in wait for it", async () => {
    const calls = mockApi({});
    render(<Home workspace={null} startError={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Opening your workspace…");
    expect(screen.getByRole("button", { name: "Try with a sample company" })).toBeDisabled();
    await userEvent.keyboard("s");
    expect(calls).toEqual([]);
  });

  it("says every answer stays a draft until a person approves it", () => {
    mockApi({ "GET /api/health": fixtures.health });
    render(<Home workspace={fixtures.workspace} startError={null} />);
    expect(screen.getByText(/Draft, not approved/)).toBeInTheDocument();
  });
});
