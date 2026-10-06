import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import Questions from "./Questions";

const props = { workspace: fixtures.workspace, onGone: () => {}, runId: "r1" };
const err = (status: number, detail: string, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json", ...headers } });

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Questions", () => {
  it("asks the one follow-up, then accepts and offers the suggested fills", async () => {
    const replies = [
      { question: { ...fixtures.questions[0], status: "follow_up", asked_count: 1, follow_up: 'To answer "Do customers manage their own keys?" the buyer also needs how often. Could you add it?' }, answer: null, suggestions: [] },
      {
        question: { ...fixtures.questions[0], status: "answered", asked_count: 2 },
        answer: { ...fixtures.rows[1].answer!, id: "a3", item_id: "i3", label: "user_confirmed" },
        suggestions: [{ id: "s1", item_id: "i9", code: "VSQ-09", question: "Are keys rotated?", label: "verified", value: "Yes", text: "Yes.", status: "open" }],
      },
    ];
    mockApi({
      "GET /api/runs/r1/questions": fixtures.questions,
      "POST /api/questions/qq1/answer": () => replies.shift(),
      "POST /api/suggestions/s1/accept": { ...fixtures.rows[1].answer!, id: "a9", item_id: "i9" },
    });
    render(<Questions {...props} />);
    const box = await screen.findByLabelText("your answer to VSQ-03");
    await userEvent.type(box, "Yes, customers can.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/also needs how often/)).toBeInTheDocument();
    await userEvent.type(box, "They rotate keys every 90 days.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("confirmed by you")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept fill for VSQ-09" }));
    expect(await screen.findByText("accepted")).toBeInTheDocument();
  });

  it("counts characters up to 4000", async () => {
    mockApi({ "GET /api/runs/r1/questions": fixtures.questions });
    render(<Questions {...props} />);
    const box = await screen.findByLabelText("your answer to VSQ-03");
    expect(box).toHaveAttribute("maxLength", "4000");
    await userEvent.type(box, "abc");
    expect(screen.getByText("3 / 4000")).toBeInTheDocument();
  });

  it("sends with Ctrl+Enter", async () => {
    const calls = mockApi({
      "GET /api/runs/r1/questions": fixtures.questions,
      "POST /api/questions/qq1/answer": { question: { ...fixtures.questions[0], status: "answered" }, answer: null, suggestions: [] },
    });
    render(<Questions {...props} />);
    await userEvent.type(await screen.findByLabelText("your answer to VSQ-03"), "Yes{Control>}{Enter}{/Control}");
    expect(await screen.findByText("confirmed by you")).toBeInTheDocument();
    expect(calls).toContain("POST /api/questions/qq1/answer");
  });

  it("says plainly when an answer filled nothing else", async () => {
    mockApi({
      "GET /api/runs/r1/questions": fixtures.questions,
      "POST /api/questions/qq1/answer": { question: { ...fixtures.questions[0], status: "answered" }, answer: null, suggestions: [] },
    });
    render(<Questions {...props} />);
    await userEvent.type(await screen.findByLabelText("your answer to VSQ-03"), "Yes");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/No other items were filled/)).toBeInTheDocument();
  });

  it("on 409 shows the reason and reloads the queue; on 429 says when to retry; the error clears on the next try", async () => {
    let list = fixtures.questions;
    const replies: Response[] = [err(409, "This question was already answered."), err(429, "Too many answers.", { "Retry-After": "7" })];
    const calls = mockApi({
      "GET /api/runs/r1/questions": () => list,
      "POST /api/questions/qq1/answer": () => replies.shift(),
    });
    render(<Questions {...props} />);
    const box = await screen.findByLabelText("your answer to VSQ-03");
    await userEvent.type(box, "Yes");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/already answered/)).toBeInTheDocument();
    expect(calls.filter((c) => c === "GET /api/runs/r1/questions")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/try again in 7 s/i)).toBeInTheDocument();
    expect(screen.queryByText(/already answered/)).not.toBeInTheDocument();
  });

  it("shows a 409 on accepting a suggestion and drops no state", async () => {
    const q = { ...fixtures.questions[0], status: "answered", suggestions: [{ id: "s1", item_id: "i9", code: "VSQ-09", question: "Are keys rotated?", label: "verified", value: "Yes", text: "Yes.", status: "open" }] };
    mockApi({ "GET /api/runs/r1/questions": [q], "POST /api/suggestions/s1/accept": err(409, "That item was answered in the meantime.") });
    render(<Questions {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept fill for VSQ-09" }));
    expect(await screen.findByText(/answered in the meantime/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept fill for VSQ-09" })).toBeInTheDocument();
  });

  it("skips a question", async () => {
    mockApi({
      "GET /api/runs/r1/questions": fixtures.questions,
      "POST /api/questions/qq1/skip": { ...fixtures.questions[0], status: "skipped" },
    });
    render(<Questions {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Skip" }));
    expect(await screen.findByText("skipped")).toBeInTheDocument();
  });

  it("focuses the question for ?item=", async () => {
    window.history.replaceState(null, "", "/?view=questions&run=r1&item=i4");
    const two = [fixtures.questions[0], { ...fixtures.questions[0], id: "qq2", item_ids: ["i4"], codes: ["VSQ-04"] }];
    mockApi({ "GET /api/runs/r1/questions": two });
    render(<Questions {...props} />);
    expect(await screen.findByLabelText("your answer to VSQ-04")).toHaveFocus();
  });

  it("drops a stale load when the run changes", async () => {
    let release: (v: unknown) => void = () => {};
    const slow = new Promise((r) => { release = r; });
    mockApi({
      "GET /api/runs/r1/questions": () => slow,
      "GET /api/runs/r2/questions": [{ ...fixtures.questions[0], id: "qq9", codes: ["VSQ-77"] }],
    });
    const { rerender } = render(<Questions {...props} />);
    rerender(<Questions {...props} runId="r2" />);
    expect(await screen.findByLabelText("your answer to VSQ-77")).toBeInTheDocument();
    release(fixtures.questions);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByLabelText("your answer to VSQ-03")).not.toBeInTheDocument();
  });
});
