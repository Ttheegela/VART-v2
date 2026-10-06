import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import { useRoute } from "../lib/route";
import EvidenceDrawer from "./EvidenceDrawer";
import RunGrid from "./RunGrid";

const base = { answerId: "a2", code: "VSQ-02", runId: "r1", onChanged: () => {} };

function narrow(on: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: on && q.includes("899"), addEventListener() {}, removeEventListener() {} }));
}

describe("EvidenceDrawer", () => {
  it("lists each cited line with its context and marks the quote", async () => {
    narrow(false);
    mockApi({ "GET /api/answers/a2": fixtures.detail });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    const fig = await screen.findByRole("figure", { name: /access-control-policy\.docx/ });
    expect(within(fig).getAllByRole("listitem")).toHaveLength(3);
    expect(within(fig).getByText("MFA is required for all workforce access.", { selector: "mark" })).toBeInTheDocument();
    expect(screen.getByText("PLACEHOLDER")).toBeInTheDocument();
    expect(screen.getByText("Draft, not approved")).toBeInTheDocument();
  });

  it("approve is disabled for a conflict", async () => {
    narrow(false);
    mockApi({ "GET /api/answers/a2": { ...fixtures.detail, label: "conflict" } });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    expect(await screen.findByRole("button", { name: "Approve" })).toBeDisabled();
  });

  it("confidence reads — for confirmed by you", async () => {
    narrow(false);
    mockApi({ "GET /api/answers/a2": { ...fixtures.detail, label: "user_confirmed", confidence: 1, statement_lines: [{ n: 1, text: "We rotate keys quarterly." }] } });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    expect((await screen.findByText("confidence")).nextElementSibling).toHaveTextContent(/^—$/);
    expect(screen.getByText("We rotate keys quarterly.")).toBeInTheDocument();
  });

  it("under 900px the drawer is a modal that traps focus and returns it", async () => {
    narrow(true);
    mockApi({ "GET /api/answers/a2": fixtures.detail });
    const onClose = vi.fn();
    render(<><button type="button">row</button><EvidenceDrawer {...base} onClose={onClose} /></>);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 8; i++) await userEvent.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("n asks for a reason and marks not applicable", async () => {
    narrow(false);
    let body: unknown;
    const changed = vi.fn();
    mockApi({
      "GET /api/answers/a2": fixtures.detail,
      "POST /api/answers/a2/not-applicable": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return { ...fixtures.rows[1].answer!, label: "na" }; },
    });
    render(<EvidenceDrawer {...base} onChanged={changed} onClose={() => {}} />);
    await screen.findByRole("figure", { name: /access-control/ });
    await userEvent.keyboard("n");
    await userEvent.type(screen.getByLabelText("reason"), "We take no card payments.{Enter}");
    expect(body).toEqual({ reason: "We take no card payments." });
    expect(changed).toHaveBeenCalled();
  });
});

describe("EvidenceDrawer in the run grid", () => {
  function Host() {
    const r = useRoute();
    return <RunGrid workspace={fixtures.workspace} onGone={() => {}} runId="r1" itemId={r.item} />;
  }
  const routes = { "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows }, "GET /api/answers/a2": fixtures.detail };

  it("Esc closes the drawer, returns focus to the row and re-enables the grid keys", async () => {
    narrow(false);
    window.history.pushState(null, "", "?view=run&run=r1");
    mockApi(routes);
    render(<Host />);
    const row = await screen.findByRole("row", { name: /VSQ-02/ });
    await userEvent.click(row);
    await screen.findByRole("figure", { name: /access-control/ });
    expect(window.location.search).toContain("item=i2");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("figure")).not.toBeInTheDocument());
    expect(window.location.search).not.toContain("item=");
    expect(screen.getByRole("row", { name: /VSQ-02/ })).toHaveFocus();
    await userEvent.keyboard("c");
    expect(screen.getByRole("button", { name: /^conflict \d+$/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("under 900px, opening from a row moves focus into the dialog and closing returns it to the row", async () => {
    narrow(true);
    window.history.pushState(null, "", "?view=run&run=r1");
    mockApi(routes);
    render(<Host />);
    await userEvent.click(await screen.findByRole("row", { name: /VSQ-02/ }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("row", { name: /VSQ-02/ })).toHaveFocus();
  });

  it("the visible close control closes it and the column is not blank while loading", async () => {
    narrow(false);
    window.history.pushState(null, "", "?view=run&run=r1&item=i2");
    mockApi(routes);
    render(<Host />);
    expect(await screen.findByText("VSQ-02 · evidence")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "close" }));
    await waitFor(() => expect(screen.queryByText("VSQ-02 · evidence")).not.toBeInTheDocument());
  });
});
