import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GapRow } from "../lib/api";
import { GAP_FOOTER, GAP_REVIEW } from "../lib/labels";
import { fixtures, mockApi } from "../test/mockApi";
import GapCheck, { coverage } from "./GapCheck";

const props = { workspace: fixtures.workspace, onGone: () => {} };
const OUTCOME = /^[A-Z]{2}\.[A-Z]{2}-\d\d /;
const FAILED = "Not checked: the model call failed twice. Press r to check again.";

describe("GapCheck", () => {
  beforeEach(() => window.history.replaceState(null, "", "?view=gap"));
  afterEach(() => vi.restoreAllMocks());

  it("counts the coverage line from the rows", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    await screen.findByRole("table", { name: "outcomes" });
    // the status line's copy and a wrapping copy in the body, so "of N" is never cut at 320px; one is read aloud
    const copies = screen.getAllByText("checked 2 · ask me 1 · not checked 1 · of 4");
    expect(copies).toHaveLength(2);
    expect(copies.filter((c) => c.getAttribute("aria-hidden") === "true")).toHaveLength(1);
    expect(coverage(fixtures.gap.rows)).toBe("checked 2 · ask me 1 · not checked 1 · of 4");
  });

  it("counts outcomes by tier, never parts", () => {
    const rows = (["checked", "ask", "not_checked"] as const).flatMap((tier, t) =>
      Array.from({ length: [31, 5, 70][t] }, (_, i) => ({ ...fixtures.gap.rows[0], csf_id: `X${t}-${i}`, tier })),
    );
    expect(coverage(rows)).toBe("checked 31 · ask me 5 · not checked 70 · of 106");
  });

  it("lists every outcome in grouped rows with the review line and the footer", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    const table = await screen.findByRole("table", { name: "outcomes" });
    expect(within(table).getAllByRole("row", { name: OUTCOME })).toHaveLength(4);
    expect(within(table).getByText("# govern / risk management strategy")).toBeInTheDocument();
    expect(within(table).getByText("# protect / data security")).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /^PR\.DS-10 / })).toHaveTextContent("not checked in this version");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("workspace/csf 2.0/core");
    expect(screen.getByText(new RegExp(`^${GAP_REVIEW}`))).toBeInTheDocument();
    expect(screen.getByText(GAP_FOOTER)).toBeInTheDocument();
  });

  it("filters by gap label and shows each label's count", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    const group = await screen.findByRole("group", { name: "filter by label" });
    expect(within(group).getByRole("button", { name: /^not checked 1$/ })).toBeInTheDocument();
    const sum = within(group).getAllByRole("button").reduce((n, b) => n + Number(b.textContent?.match(/(\d+)$/)?.[1]), 0);
    expect(sum).toBe(fixtures.gap.rows.length);
    const gap = within(group).getByRole("button", { name: /^gap 1$/ });
    await userEvent.click(gap);
    expect(gap).toHaveAttribute("aria-pressed", "true");
    const shown = screen.getAllByRole("row", { name: OUTCOME }).map((r) => r.getAttribute("aria-label")?.slice(0, 8));
    expect(shown).toEqual(["PR.DS-01"]);
  });

  it("shows a not applicable outcome as not applicable on either tier (adversary-1 I1)", async () => {
    const [ask, checked] = fixtures.gap.rows;
    const na = (r: GapRow, label: GapRow["label"]): GapRow => ({ ...r, label, not_applicable: true, explanation: "Out of scope: no customer data." });
    mockApi({ "GET /api/gap/core": { ...fixtures.gap, rows: [na(ask, "not_answered"), na(checked, null)] } });
    render(<GapCheck {...props} />);
    const table = await screen.findByRole("table", { name: "outcomes" });
    for (const id of [/^GV\.RM-02 /, /^PR\.DS-11 /]) {
      const row = within(table).getByRole("row", { name: id });
      expect(row).toHaveTextContent("not applicable");
      expect(row).not.toHaveTextContent("not answered");
    }
    const group = screen.getByRole("group", { name: "filter by label" });
    expect(within(group).getByRole("button", { name: /^not applicable 2$/ })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: /^not answered 0$/ })).toBeInTheDocument();
  });

  it("a failed outcome shows the failure sentence, not a gap label (adversary-1 M4)", async () => {
    const failed: GapRow = { ...fixtures.gap.rows[2], label: null, answer_id: "a-x", explanation: FAILED };
    mockApi({ "GET /api/gap/core": { ...fixtures.gap, rows: [failed] } });
    render(<GapCheck {...props} />);
    const row = await screen.findByRole("row", { name: /^PR\.DS-01 / });
    expect(row).toHaveTextContent(FAILED);
    expect(within(row).queryByText("gap")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /^no result 1$/ });
    await userEvent.click(toggle);
    expect(screen.getByRole("row", { name: /^PR\.DS-01 / })).toBeInTheDocument();
  });

  it("scope keys switch the scope", async () => {
    const calls = mockApi({
      "GET /api/gap/core": fixtures.gap,
      "GET /api/gap/protect": { ...fixtures.gap, scope: "protect", rows: fixtures.gap.rows.slice(1) },
    });
    const { rerender } = render(<GapCheck {...props} />);
    await screen.findByRole("table", { name: "outcomes" });
    await userEvent.keyboard("p");
    expect(window.location.search).toBe("?view=gap&scope=protect");
    rerender(<GapCheck {...props} scope="protect" />);
    await waitFor(() => expect(calls).toContain("GET /api/gap/protect"));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("workspace/csf 2.0/protect");
  });

  it("r starts the check and the step loop fills the rows", async () => {
    const done = fixtures.gap.run!;
    const running = { ...fixtures.gap, run: { ...done, status: "running" as const, done: 0 } };
    let gets = 0;
    const calls = mockApi({
      "GET /api/gap/core": () => (gets++ === 0 ? { ...fixtures.gap, run: null } : gets === 2 ? running : fixtures.gap),
      "POST /api/gap/core/run": running.run,
      "POST /api/runs/r9/step": { run: done, answered: [] },
    });
    render(<GapCheck {...props} />);
    await screen.findByRole("button", { name: "Run gap check" });
    await userEvent.keyboard("r");
    expect(await screen.findByText(/2 of 2 checked · done/)).toBeInTheDocument();
    expect(calls).toEqual(expect.arrayContaining(["POST /api/gap/core/run", "POST /api/runs/r9/step"]));
    expect(screen.getByRole("button", { name: "Check again" })).toBeEnabled();
  });

  it("r with nothing changed says so (adversary-1 M7)", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap, "POST /api/gap/core/run": fixtures.gap.run });
    render(<GapCheck {...props} />);
    await screen.findByRole("button", { name: "Check again" });
    await userEvent.keyboard("r");
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing changed since the last check.");
  });

  it("e waits while the check is running, and says why", async () => {
    const running = { ...fixtures.gap, run: { ...fixtures.gap.run!, status: "running" as const, done: 0 } };
    mockApi({ "GET /api/gap/core": running, "POST /api/runs/r9/step": () => new Promise(() => {}) });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<GapCheck {...props} />);
    expect(await screen.findByRole("button", { name: "Export xlsx" })).toBeDisabled();
    expect(screen.getByText("export when the check is done")).toBeInTheDocument();
    await userEvent.keyboard("e");
    expect(click).not.toHaveBeenCalled();
  });

  it("a scope switch puts the cursor back on the first row", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap, "GET /api/gap/protect": { ...fixtures.gap, scope: "protect" } });
    const { rerender } = render(<GapCheck {...props} />);
    await screen.findByRole("table", { name: "outcomes" });
    await userEvent.keyboard("jj");
    expect(screen.getByRole("row", { name: /^PR\.DS-01 / })).toHaveAttribute("tabindex", "0");
    rerender(<GapCheck {...props} scope="protect" />);
    expect(await screen.findByRole("row", { name: /^GV\.RM-02 / })).toHaveAttribute("tabindex", "0");
  });

  it("e downloads the gap report of the run", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { container } = render(<GapCheck {...props} />);
    await screen.findByRole("button", { name: "Check again" });
    expect(container.querySelector("a[download]")).toHaveAttribute("href", "/api/runs/r9/export");
    await userEvent.keyboard("e");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("a click or enter on a row opens that outcome", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    await userEvent.click(await screen.findByRole("row", { name: /^PR\.DS-11 / }));
    expect(window.location.search).toBe("?view=gap&item=PR.DS-11&scope=core");
  });

  it("the outcome in the route opens its inspector and esc goes back to the list", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    mockApi({ "GET /api/gap/core": fixtures.gap, "GET /api/answers/a-PR.DS-11": fixtures.gapDetail });
    render(<GapCheck {...props} outcome="PR.DS-11" />);
    expect(await screen.findByRole("complementary")).toHaveTextContent("PR.DS-11 · gap check");
    await userEvent.keyboard("p"); // list keys are off while the inspector is open
    expect(window.location.search).toBe("?view=gap");
    await userEvent.keyboard("{Escape}");
    expect(window.location.search).toBe("?view=gap&scope=core");
  });
});
