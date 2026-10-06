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

describe("EvidenceDrawer fixes", () => {
  const approved = { ...fixtures.rows[1].answer!, approved: true };
  const err = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });

  it("a switch to another answer never shows the old one, and a slow old load cannot land", async () => {
    narrow(false);
    let release: () => void = () => {};
    const slow = new Promise<void>((r) => { release = r; });
    mockApi({
      "GET /api/answers/a2": async () => { await slow; return fixtures.detail; },
      "GET /api/answers/a1": { ...fixtures.detail, id: "a1", item: { ...fixtures.detail.item, question: "Second question?" } },
    });
    const { rerender } = render(<EvidenceDrawer {...base} onClose={() => {}} />);
    rerender(<EvidenceDrawer {...base} answerId="a1" code="VSQ-01" onClose={() => {}} />);
    expect(await screen.findByText("Second question?")).toBeInTheDocument();
    release();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Second question?")).toBeInTheDocument();
    expect(screen.queryByText("Is MFA enforced for all workforce access?")).not.toBeInTheDocument();
  });

  it("approve succeeds, refreshes and notifies; in narrow mode Tab stays inside afterwards", async () => {
    narrow(true);
    const changed = vi.fn();
    let done = false;
    mockApi({
      "GET /api/answers/a2": () => ({ ...fixtures.detail, approved: done }),
      "POST /api/answers/a2/approve": () => { done = true; return approved; },
    });
    render(<EvidenceDrawer {...base} onChanged={changed} onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(changed).toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveFocus(); // the pressed Approve is gone; focus moves to the dialog, not to the body
    for (let i = 0; i < 6; i++) { await userEvent.tab(); expect(dialog.contains(document.activeElement)).toBe(true); }
  });

  it("a 409 on approve is shown, and cleared by the next success", async () => {
    narrow(false);
    let fail = true;
    mockApi({
      "GET /api/answers/a2": fixtures.detail,
      "POST /api/answers/a2/approve": () => (fail ? err(409, "Answer the question first.") : approved),
    });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Answer the question first.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("a failed not-applicable keeps the form open and shows the error", async () => {
    narrow(false);
    mockApi({ "GET /api/answers/a2": fixtures.detail, "POST /api/answers/a2/not-applicable": err(500, "Could not save.") });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    await screen.findByRole("figure", { name: /access-control/ });
    await userEvent.keyboard("n");
    await userEvent.type(screen.getByLabelText("reason"), "No cards.{Enter}");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("reason")).toBeInTheDocument();
  });

  it("a conflict shows each side under a heading with its stance and date", async () => {
    narrow(false);
    const c0 = fixtures.detail.citations[0];
    mockApi({
      "GET /api/answers/a2": {
        ...fixtures.detail, label: "conflict",
        citations: [c0, { ...c0, filename: "old-policy.docx", stance: "no" }],
        conflict: { rule: "date", sides: [{ citations: [0], date: "2026-01-15", stance: "yes" }, { citations: [1], date: "2025-01-15", stance: "no" }] },
      },
    });
    render(<EvidenceDrawer {...base} onClose={() => {}} />);
    const yes = await screen.findByRole("heading", { name: "yes · 2026-01-15" });
    const no = screen.getByRole("heading", { name: "no · 2025-01-15" });
    expect(within(yes.parentElement!).getByRole("figure", { name: /access-control/ })).toBeInTheDocument();
    expect(within(no.parentElement!).getByRole("figure", { name: /old-policy/ })).toBeInTheDocument();
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
