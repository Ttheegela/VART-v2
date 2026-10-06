import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { QuestionOut } from "../lib/api";
import { fixtures, mockApi } from "../test/mockApi";
import GapDrawer from "./GapDrawer";

const [ask, checked, , unchecked] = fixtures.gap.rows;
const err = (status: number, detail: string) =>
  new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } });
const base = { runId: "r9", controlsUrl: fixtures.gap.controls_url, onClose: () => {}, onChanged: () => {} };

describe("GapDrawer", () => {
  beforeEach(() => vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} })));

  it("shows NIST's verbatim outcome, its link, the controls as links and each part's status", async () => {
    mockApi({ "GET /api/answers/a-PR.DS-11": fixtures.gapDetail });
    render(<GapDrawer {...base} row={checked} />);
    const drawer = screen.getByRole("complementary");
    expect(within(drawer).getByRole("heading", { level: 2 })).toHaveTextContent(checked.outcome);
    expect(within(drawer).getByRole("link", { name: "NIST CSF 2.0 reference tool" })).toHaveAttribute("href", checked.source_url);
    expect(within(drawer).getByRole("link", { name: "CP-09" })).toHaveAttribute("href", fixtures.gap.controls_url);
    expect(await within(drawer).findByText("parts (2)")).toBeInTheDocument();
    expect(within(drawer).getByText("Are backups of data created?").closest("li")).toHaveTextContent(/covered.*\[1\]/);
    expect(within(drawer).getByText("Are backups of data tested?").closest("li")).toHaveTextContent("gap");
    expect(within(drawer).getByRole("figure", { name: "[1] backup-policy.docx" })).toHaveTextContent("draft"); // carry d
  });

  it("an Ask-me outcome is answered here and then confirmed by you", async () => {
    const onChanged = vi.fn();
    const q: QuestionOut = {
      ...fixtures.questions[0], id: "qq9", run_id: "r9", item_ids: ["i-GV.RM-02"], codes: ["GV.RM-02"],
      text: "Has your organization set risk appetite and risk tolerance statements?",
    };
    mockApi({
      "GET /api/answers/a-GV.RM-02": { ...fixtures.detail, id: "a-GV.RM-02", label: "unknown", value: null, text: "", citations: [], dropped: [], parts: [] },
      "GET /api/runs/r9/questions": [q],
      "POST /api/questions/qq9/answer": {
        question: { ...q, status: "answered", asked_count: 1 },
        answer: { ...fixtures.rows[1].answer!, id: "a-GV.RM-02", label: "user_confirmed" },
        suggestions: [],
      },
    });
    render(<GapDrawer {...base} row={ask} onChanged={onChanged} />);
    await userEvent.type(await screen.findByLabelText("your answer to GV.RM-02"), "Yes. The board approved a risk appetite statement.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("confirmed by you")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("says an Ask-me answer becomes a citable statement, and names the part a fill is for", async () => {
    const q: QuestionOut = {
      ...fixtures.questions[0], id: "qq9", run_id: "r9", item_ids: ["i-GV.RM-02"], codes: ["GV.RM-02"], text: "Risk appetite?",
    };
    const fill = { id: "s1", item_id: "i-PR.DS-11", code: "PR.DS-11", part: 2, question: "Are backups of data tested?", label: "verified" as const, value: "Yes" as const, status: "open" as const };
    mockApi({
      "GET /api/answers/a-GV.RM-02": { ...fixtures.detail, id: "a-GV.RM-02", label: "unknown", value: null, text: "", citations: [], dropped: [], parts: [] },
      "GET /api/runs/r9/questions": [{ ...q, suggestions: [fill] }],
    });
    render(<GapDrawer {...base} row={ask} />);
    // adversary-1 M9
    expect(await screen.findByText("Your answer is saved as a dated statement and can be cited in your questionnaires.")).toBeInTheDocument();
    // preflight I3: the fill's question is its part's wording, and the card says which part
    expect(screen.getByText("Are backups of data tested?").closest("li")).toHaveTextContent(/PR\.DS-11.*part 2/);
    // adversary-2 M4: a part's fill speaks the gap check's words
    expect(screen.getByText("Are backups of data tested?").closest("li")).toHaveTextContent("covered");
    expect(screen.getByText("Are backups of data tested?").closest("li")).not.toHaveTextContent("verified");
  });

  it("a 409 on the Ask-me card reloads the inspector, so the card shows the question as it is now (Task 6 review M2)", async () => {
    const q: QuestionOut = { ...fixtures.questions[0], id: "qq9", run_id: "r9", item_ids: ["i-GV.RM-02"], codes: ["GV.RM-02"], text: "Risk appetite?" };
    const calls = mockApi({
      "GET /api/answers/a-GV.RM-02": { ...fixtures.detail, id: "a-GV.RM-02", label: "unknown", value: null, text: "", citations: [], dropped: [], parts: [] },
      "GET /api/runs/r9/questions": [q],
      "POST /api/questions/qq9/answer": () => err(409, "This question was already answered."),
    });
    render(<GapDrawer {...base} row={ask} />);
    await userEvent.type(await screen.findByLabelText("your answer to GV.RM-02"), "Yes");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/already answered/)).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c === "GET /api/runs/r9/questions")).toHaveLength(2));
  });

  it("a not applicable Ask-me outcome shows no question card (Task 6 review M3)", async () => {
    const q: QuestionOut = { ...fixtures.questions[0], id: "qq9", run_id: "r9", item_ids: ["i-GV.RM-02"], codes: ["GV.RM-02"], text: "Risk appetite?" };
    mockApi({
      "GET /api/answers/a-GV.RM-02": { ...fixtures.detail, id: "a-GV.RM-02", label: "unknown", value: null, text: "", citations: [], dropped: [], parts: [] },
      "GET /api/runs/r9/questions": [q],
    });
    render(<GapDrawer {...base} row={{ ...ask, not_applicable: true }} />);
    expect(screen.getByText("not applicable")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByLabelText("your answer to GV.RM-02")).not.toBeInTheDocument();
    expect(screen.queryByText(/dated statement/)).not.toBeInTheDocument();
  });

  it("a part citation missing from the sources gets no [0] footnote (Task 6 review M4)", async () => {
    mockApi({ "GET /api/answers/a-PR.DS-11": { ...fixtures.gapDetail, citations: [] } });
    render(<GapDrawer {...base} row={checked} />);
    expect(await screen.findByText("parts (2)")).toBeInTheDocument();
    expect(screen.getByText("Are backups of data created?").closest("li")).not.toHaveTextContent("[0]");
  });

  it("a not applicable outcome reads not applicable, and a failed one shows its sentence and no label", async () => {
    mockApi({ "GET /api/answers/a-PR.DS-11": { ...fixtures.gapDetail, parts: [], citations: [] } });
    const { unmount } = render(<GapDrawer {...base} row={{ ...checked, label: null, not_applicable: true, explanation: "Out of scope." }} />);
    expect(screen.getByText("not applicable")).toBeInTheDocument(); // adversary-1 I1
    unmount();
    const failed = "Not checked: the model call failed twice. Press r to check again.";
    render(<GapDrawer {...base} row={{ ...checked, label: null, explanation: failed }} />);
    expect(screen.getByText(failed)).toBeInTheDocument(); // adversary-1 M4
    expect(screen.getByText("label").nextElementSibling).toHaveTextContent("—");
  });

  it("shows both sides of a documents-disagree outcome with their footnotes", async () => {
    const other = { ...fixtures.gapDetail.citations[0], filename: "backup-log.xlsx", stance: "no" as const };
    mockApi({
      "GET /api/answers/a-PR.DS-11": {
        ...fixtures.gapDetail, citations: [fixtures.gapDetail.citations[0], other],
        conflict: { rule: "documents-disagree", sides: [{ stance: "yes", date: "2026-01-15", citations: [0] }, { stance: "no", date: null, citations: [1] }] },
      },
    });
    render(<GapDrawer {...base} row={{ ...checked, label: "documents_disagree" }} />);
    expect(await screen.findByText("no · undated")).toBeInTheDocument(); // adversary-1 N4
    expect(screen.getByRole("figure", { name: "[2] backup-log.xlsx" })).toBeInTheDocument();
  });

  it("a not-checked outcome says so and asks the API for nothing", () => {
    const calls = mockApi({});
    render(<GapDrawer {...base} row={unchecked} />);
    expect(screen.getByText("not checked in this version")).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("esc closes", async () => {
    const onClose = vi.fn();
    mockApi({});
    render(<GapDrawer {...base} row={unchecked} onClose={onClose} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
