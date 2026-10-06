import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useKeys } from "../lib/keys";
import { go } from "../lib/route";
import { STEPS, maybeStartTour, startTour } from "../lib/tour";
import { fixtures, mockApi } from "../test/mockApi";
import GapCheck from "../views/GapCheck";
import Questions from "../views/Questions";
import { Shell } from "./Shell";
import Tour from "./Tour";

function Drawer({ onEsc }: { onEsc: () => void }) {
  useKeys({ Escape: onEsc });
  return <aside aria-label="drawer" />;
}

const ctx = { runId: "r1", conflictItem: "i1" };
const dialog = () => screen.queryByRole("dialog", { name: "guided tour" });
const at = (n: number) => expect(screen.getByText(`step ${n} of ${STEPS.length}`)).toBeInTheDocument();
const narrow = (on: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: on && q.includes("899"), addEventListener() {}, removeEventListener() {} }));

describe("Tour", () => {
  it("has ten steps in app order", () => {
    expect(STEPS.map((s) => s.target)).toEqual([
      "brand", "documents", "questionnaire", "filters", "drawer", "questions", "export", "audit", "coverage", "legal",
    ]);
  });

  it("walks every step with Next, Back goes back, Done closes it, and it calls no API", async () => {
    const calls = mockApi({});
    render(<Tour />);
    act(() => startTour(ctx));
    for (const [i, s] of STEPS.entries()) {
      at(i + 1);
      expect(screen.getByRole("heading", { name: s.title })).toBeInTheDocument();
      if (i < STEPS.length - 1) await userEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    at(STEPS.length - 1);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(dialog()).toBeNull();
    expect(calls).toEqual([]); // runs on the precomputed run: no request, no model call
  });

  it("moves between views with the existing routes and adds no history entries", async () => {
    render(<Tour />);
    const before = window.history.length;
    act(() => startTour(ctx));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(window.location.search).toBe("?view=workspace");
    for (let i = 0; i < 3; i++) await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(window.location.search).toBe("?view=run&run=r1&item=i1"); // the evidence step opens a conflict
    expect(window.history.length).toBe(before); // replaceState: browser Back does not walk the tour (adversary M10)
  });

  it("under 900 px the evidence step stays on the grid, and a modal drawer closes the tour (adversary M9)", async () => {
    narrow(true);
    render(<Tour />);
    act(() => startTour(ctx));
    for (let i = 0; i < 4; i++) await userEvent.click(screen.getByRole("button", { name: "Next" }));
    at(5);
    expect(window.location.search).toBe("?view=run&run=r1");
    act(() => go({ view: "run", run: "r1", item: "i1" })); // the visitor opens a row: a full-screen aria-modal drawer
    expect(dialog()).toBeNull();
  });

  it("→ and Enter move on, ← moves back, Esc skips, and focus sits on Next", async () => {
    render(<Tour />);
    act(() => startTour(ctx));
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    at(2);
    await userEvent.keyboard("{Enter}");
    at(3);
    await userEvent.keyboard("{ArrowLeft}");
    at(2);
    expect(screen.getByRole("status")).toHaveTextContent(`Step 2 of ${STEPS.length}: ${STEPS[1].title}`);
    await userEvent.keyboard("{Escape}");
    expect(dialog()).toBeNull();
  });

  it("gives focus back to where it was when it closes", async () => {
    render(<><button type="button">row</button><Tour /></>);
    screen.getByRole("button", { name: "row" }).focus();
    act(() => startTour(ctx));
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "row" })).toHaveFocus();
  });

  it("takes keys only inside its card: Enter on a page button presses that button (adversary I4)", async () => {
    const pressed = vi.fn();
    render(<><button type="button" onClick={pressed}>approve</button><Tour /></>);
    act(() => startTour(ctx));
    screen.getByRole("button", { name: "approve" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(pressed).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{ArrowRight}{Escape}");
    at(1); // the page's keys stay the page's
    expect(dialog()).not.toBeNull();
  });

  it("starts every time the sample run opens, Skip closes it for that visit only, and it never touches storage", async () => {
    const get = vi.spyOn(Storage.prototype, "getItem");
    const set = vi.spyOn(Storage.prototype, "setItem");
    render(<Tour />);
    act(() => maybeStartTour(ctx));
    expect(dialog()).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    act(() => maybeStartTour(ctx)); // the same run shown again in this visit (the tour's own moves, a view key)
    expect(dialog()).toBeNull();
    act(() => maybeStartTour({ runId: "r7", conflictItem: null })); // the sample opened again
    expect(dialog()).not.toBeNull();
    act(() => go({ view: "workspace" }));
    await userEvent.keyboard("{Escape}");
    act(() => startTour(ctx)); // t, the Tour button
    expect(dialog()).not.toBeNull();
    expect(get).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });

  it("closes when the visitor opens another run, so it never sits on a live run", () => {
    render(<Tour />);
    act(() => startTour(ctx));
    act(() => go({ view: "run", run: "r2" }));
    expect(dialog()).toBeNull();
  });

  it("closes while a gap check runs (adversary I5)", async () => {
    const running = { ...fixtures.gap, run: { ...fixtures.gap.run!, status: "running" as const, done: 0 } };
    mockApi({ "GET /api/gap/core": running, "POST /api/runs/r9/step": () => new Promise(() => {}) });
    render(<><GapCheck workspace={fixtures.workspace} onGone={() => {}} /><Tour /></>);
    act(() => startTour(ctx));
    expect(dialog()).not.toBeNull();
    await screen.findByText("Checking.");
    expect(dialog()).toBeNull();
  });

  it("keeps focus on Next when a view focuses its own field on load", async () => {
    mockApi({ "GET /api/runs/r1/questions": fixtures.questions });
    render(<><Questions workspace={fixtures.workspace} onGone={() => {}} runId="r1" /><Tour /></>);
    act(() => startTour(ctx));
    await screen.findByLabelText(/^your answer to /);
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
  });

  it("closes the moment a gap check starts, before the request answers (review I2)", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap, "POST /api/gap/core/run": () => new Promise(() => {}) });
    render(<><GapCheck workspace={fixtures.workspace} onGone={() => {}} /><Tour /></>);
    await screen.findByRole("button", { name: "Check again" });
    act(() => startTour(ctx));
    expect(dialog()).not.toBeNull();
    await userEvent.keyboard("r"); // focus is on Next: r reaches the page's key map
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled(); // the request is still pending
    expect(dialog()).toBeNull();
  });

  it("Esc inside the card closes only the tour, never the drawer under it (review M6)", async () => {
    const esc = vi.fn();
    render(<><Drawer onEsc={esc} /><Tour /></>);
    act(() => startTour(ctx));
    await userEvent.keyboard("{Escape}");
    expect(dialog()).toBeNull();
    expect(esc).not.toHaveBeenCalled();
  });

  it("the page gets room under the card while the tour is open, so the last rows stay reachable (review M1)", () => {
    render(<><Shell mode="RUN" cursor="" hints={[]} expiresAt={null}>x</Shell><Tour /></>);
    expect(screen.getByRole("main")).not.toHaveClass("pb-80");
    act(() => startTour(ctx));
    expect(screen.getByRole("main")).toHaveClass("pb-80");
  });

  it("says the audit log shows what changed and when (review M3)", () => {
    expect(STEPS[7].body).toContain("what changed and when");
  });

  it("says the gap check is precomputed only for the untouched sample company", () => {
    expect(STEPS[8].body).toContain("the untouched sample company");
    expect(STEPS[8].body).not.toContain("instant");
  });
});
