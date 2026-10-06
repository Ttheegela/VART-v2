import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { RunRowsOut } from "../lib/api";
import { RUN_CLOSED } from "../lib/labels";
import { fixtures, mockApi } from "../test/mockApi";
import RunGrid, { mergeRows, useStepLoop } from "./RunGrid";

const props = { workspace: fixtures.workspace, onGone: () => {}, runId: "r1" };

describe("RunGrid", () => {
  it("shows one row per item with label, confidence, sources and approval in words", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    const row = await screen.findByRole("row", { name: /VSQ-02/ });
    expect(within(row).getByText("verified")).toBeInTheDocument();
    expect(within(row).getByText("0.90")).toBeInTheDocument();
    expect(within(row).getByText("Draft, not approved")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /VSQ-03/ })).getByText("answering…")).toBeInTheDocument();
    expect(screen.getByText("# access control")).toBeInTheDocument();
  });

  it("a run closed as abandoned says why and how to start again (Plan 4 Task 4)", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: { ...fixtures.run, status: "failed" }, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    expect(await screen.findByText(RUN_CLOSED)).not.toHaveClass("sr-only");
  });

  it("approve all says how many edited answers it left for a look", async () => {
    mockApi({
      "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows },
      "POST /api/runs/r1/approve-verified": { approved: 1, skipped_edited: 2 },
    });
    render(<RunGrid {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: /Approve all verified/ }));
    expect(await screen.findByText("2 edited answers left for you to approve one by one.")).toBeInTheDocument();
  });

  it("export is a download link click, never a page navigation", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    await screen.findByRole("row", { name: /VSQ-02/ });
    await userEvent.keyboard("e");
    expect(click).toHaveBeenCalledTimes(1);
    expect(click.mock.contexts[0]).toHaveAttribute("download");
    expect(click.mock.contexts[0]).toHaveAttribute("href", "/api/runs/r1/export");
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
    click.mockRestore();
  });

  it("shows a dash for the confidence of answers no model scored", async () => {
    const rows = [
      { ...fixtures.rows[0], answer: { ...fixtures.rows[0].answer!, label: "user_confirmed" as const } },
      { ...fixtures.rows[1], answer: { ...fixtures.rows[1].answer!, label: "na" as const } },
    ];
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows } });
    render(<RunGrid {...props} />);
    expect(within(await screen.findByRole("row", { name: /VSQ-01/ })).getByText("—")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /VSQ-02/ })).getByText("—")).toBeInTheDocument();
  });

  it("filters by label with its key and searches with /", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    await screen.findByRole("row", { name: /VSQ-02/ });
    await userEvent.keyboard("c");
    expect(screen.queryByRole("row", { name: /VSQ-02/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^conflict \d+$/i })).toHaveAttribute("aria-pressed", "true");
    await userEvent.keyboard("c/");
    await userEvent.keyboard("mfa");
    expect(screen.getAllByRole("row", { name: /VSQ-/ })).toHaveLength(1);
  });

  it("typing in search does not toggle filters", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    await screen.findByRole("row", { name: /VSQ-02/ });
    await userEvent.keyboard("/");
    await userEvent.keyboard("vpc");
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("a 404 on load means the workspace is gone", async () => {
    mockApi({ "GET /api/runs/r1/answers": new Response(JSON.stringify({ detail: "Not found." }), { status: 404 }) });
    const onGone = vi.fn();
    render(<RunGrid {...props} onGone={onGone} />);
    await waitFor(() => expect(onGone).toHaveBeenCalled());
  });

  it("a running run resumes on mount and stops when done", async () => {
    const running = { ...fixtures.run, status: "running" as const, done: 2 };
    const answered = [{ ...fixtures.rows[2], answer: { ...fixtures.rows[1].answer!, id: "a3", item_id: "i3", label: "unknown" as const, confidence: 0 } }];
    const calls = mockApi({
      "GET /api/runs/r1/answers": { run: running, rows: fixtures.rows },
      "POST /api/runs/r1/step": { run: fixtures.run, answered },
    });
    render(<RunGrid {...props} />);
    const row = await screen.findByRole("row", { name: /VSQ-03/ });
    expect(await within(row).findByText("unknown")).toBeInTheDocument();
    expect(calls.filter((c) => c === "POST /api/runs/r1/step")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Run done: 3 of 3 answered.");
  });

  it("under StrictMode every claimed item fills in and only one step is in flight at a time", async () => {
    const running = { ...fixtures.run, status: "running" as const, done: 2 };
    const answered = [{ ...fixtures.rows[2], answer: { ...fixtures.rows[1].answer!, id: "a3", item_id: "i3", label: "unknown" as const, confidence: 0 } }];
    let inFlight = 0;
    let most = 0;
    let claimed = false;
    const calls = mockApi({
      "GET /api/runs/r1/answers": { run: running, rows: fixtures.rows },
      // like the server: a claimed item is returned once; later steps see nothing left to claim
      "POST /api/runs/r1/step": async () => {
        most = Math.max(most, ++inFlight);
        await new Promise((r) => setTimeout(r, 30));
        inFlight -= 1;
        const first = !claimed;
        claimed = true;
        return { run: fixtures.run, answered: first ? answered : [] };
      },
    });
    render(<StrictMode><RunGrid {...props} /></StrictMode>);
    const row = await screen.findByRole("row", { name: /VSQ-03/ });
    expect(await within(row).findByText("unknown")).toBeInTheDocument();
    expect(most).toBe(1);
    expect(calls.filter((c) => c === "POST /api/runs/r1/step")).toHaveLength(1);
  });

  it("a 404 on a step means the workspace is gone", async () => {
    const onGone = vi.fn();
    mockApi({
      "GET /api/runs/r1/answers": { run: { ...fixtures.run, status: "running" }, rows: fixtures.rows },
      "POST /api/runs/r1/step": new Response(JSON.stringify({ detail: "gone" }), { status: 404 }),
    });
    render(<RunGrid {...props} onGone={onGone} />);
    await waitFor(() => expect(onGone).toHaveBeenCalled());
  });

  it("Re-run live answered 409 on this still-running run resumes its loop and shows no error (Ruling 12)", async () => {
    const running = { ...fixtures.run, status: "running" as const, done: 2 };
    let n = 0;
    const calls = mockApi({
      "GET /api/runs/r1/answers": { run: running, rows: fixtures.rows },
      "POST /api/runs/r1/step": () =>
        ++n === 1 ? new Response("{}", { status: 500 }) : { run: fixtures.run, answered: [] },
      "POST /api/questionnaires/q1/runs": new Response(JSON.stringify({ detail: "A run of this questionnaire is still going; wait for it to finish first." }), { status: 409 }),
    });
    render(<RunGrid {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed (500)");
    await userEvent.click(screen.getByRole("button", { name: /Re-run live/ }));
    await waitFor(() => expect(calls.filter((c) => c === "POST /api/runs/r1/step")).toHaveLength(2));
    expect(calls).toContain("POST /api/questionnaires/q1/runs");
    expect(await screen.findByRole("status")).toHaveTextContent("Run done: 3 of 3 answered.");
    expect(screen.queryByText(/still going/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a 429 stops the loop and says why", async () => {
    mockApi({
      "GET /api/runs/r1/answers": { run: { ...fixtures.run, status: "running" }, rows: fixtures.rows },
      "POST /api/runs/r1/step": new Response(JSON.stringify({ detail: "The model budget for this workspace is used up for this hour; the run can resume then." }), { status: 429, headers: { "Retry-After": "600" } }),
    });
    render(<RunGrid {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: The model budget");
    expect(screen.getAllByRole("row", { name: /VSQ-/ })).toHaveLength(3);
  });

  it("hostile text renders as text", async () => {
    const evil = [{ ...fixtures.rows[1], answer: { ...fixtures.rows[1].answer!, text: "<img src=x onerror=alert(1)> <PERSON>" } }];
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: evil } });
    render(<RunGrid {...props} />);
    expect(await screen.findByText("<img src=x onerror=alert(1)> <PERSON>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("j, k and enter move the cursor and open the drawer", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows }, "GET /api/answers/a2": fixtures.detail });
    render(<RunGrid {...props} />);
    await screen.findByRole("row", { name: /VSQ-01/ });
    await userEvent.keyboard("j{Enter}");
    expect(window.location.search).toContain("item=i2");
  });

  it("enter on a focused button presses the button, not the row", async () => {
    window.history.replaceState(null, "", "?view=run&run=r1");
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<RunGrid {...props} />);
    await screen.findByRole("row", { name: /VSQ-01/ });
    screen.getByRole("button", { name: /^verified \d+$/ }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: /^verified \d+$/ })).toHaveAttribute("aria-pressed", "true");
    expect(window.location.search).not.toContain("item=");
  });

  it("mergeRows replaces answered items in place", () => {
    const merged = mergeRows(fixtures.rows, [{ ...fixtures.rows[2], answer: fixtures.rows[1].answer }]);
    expect(merged.map((r) => r.answer?.id ?? null)).toEqual(["a1", "a2", "a2"]);
    expect(merged[0]).toBe(fixtures.rows[0]); // unchanged rows keep their identity, so memoized rows skip render
  });
  it("re-run live asks for a live run, and a copied run says it is precomputed", async () => {
    const searches: string[] = [];
    mockApi({
      "GET /api/runs/r1/answers": { run: { ...fixtures.run, precomputed: true, cost_usd: 0 }, rows: fixtures.rows },
      "GET /api/questionnaires": [],
      "POST /api/questionnaires/q1/runs": (_init: RequestInit | undefined, url: URL) => {
        searches.push(url.search);
        return { ...fixtures.run, id: "r2", status: "running", done: 0, precomputed: false };
      },
    });
    render(<RunGrid {...props} />);
    expect(await screen.findByText(/precomputed sample answers/)).toBeInTheDocument();
    await userEvent.keyboard("r");
    await waitFor(() => expect(searches).toEqual(["?live=true"]));
  });
});

describe("useStepLoop", () => {
  const running = { ...fixtures.run, status: "running" as const };
  const start: RunRowsOut = { run: running, rows: fixtures.rows };
  const answered = [{ ...fixtures.rows[2], answer: { ...fixtures.rows[1].answer!, id: "a3", item_id: "i3" } }];

  it("backs off from 2 s to 10 s while steps come back empty, and resets once answers arrive", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const replies = [[], [], [], [], [], answered, [], []];
    const times: number[] = [];
    mockApi({
      "POST /api/runs/r1/step": () => {
        times.push(Date.now());
        const out = replies.shift();
        return { run: replies.length ? running : fixtures.run, answered: out };
      },
    });
    const onData = vi.fn();
    renderHook(() => useStepLoop("r1", start, onData));
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(times.slice(1).map((t, i) => t - times[i])).toEqual([2000, 4000, 8000, 10_000, 10_000, 0, 2000]);
    expect(onData.mock.lastCall?.[0].run.status).toBe("done");
  });

  it("under StrictMode a mount with data merges the in-flight step and never sends a second one at once", async () => {
    let inFlight = 0;
    let most = 0;
    let claimed = false;
    const calls = mockApi({
      // like the server: a claimed item is returned once; later steps see nothing left to claim
      "POST /api/runs/r1/step": async () => {
        most = Math.max(most, ++inFlight);
        await new Promise((r) => setTimeout(r, 30));
        inFlight -= 1;
        const first = !claimed;
        claimed = true;
        return { run: fixtures.run, answered: first ? answered : [] };
      },
    });
    const { result } = renderHook(() => {
      const [d, setD] = useState<RunRowsOut | null>(start);
      useStepLoop("r1", d, setD);
      return d;
    }, { wrapper: StrictMode });
    await waitFor(() => expect(result.current?.run.status).toBe("done"));
    expect(result.current?.rows[2].answer?.id).toBe("a3");
    expect(most).toBe(1);
    expect(calls).toHaveLength(1);
  });

  it("a 429 waits for Retry-After, shows the scope sentence, then resumes", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const sentence = "This network has used its model calls for this hour; the run can resume then.";
    let n = 0;
    const calls = mockApi({
      "POST /api/runs/r1/step": () =>
        ++n === 1
          ? new Response(JSON.stringify({ detail: sentence }), { status: 429, headers: { "Retry-After": "30" } })
          : { run: fixtures.run, answered },
    });
    const { result } = renderHook(() => {
      const [d, setD] = useState<RunRowsOut | null>(start);
      return useStepLoop("r1", d, setD);
    });
    await act(() => vi.advanceTimersByTimeAsync(29_000));
    expect(result.current.error).toBe(sentence);
    expect(result.current.running).toBe(true);
    expect(calls).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(calls).toHaveLength(2);
    expect(result.current.error).toBeNull();
    expect(result.current.running).toBe(false);
  });

  it("a 404 GONE stops the loop and says to reload", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const gone = "Your workspace has expired or was reset; reload the page to start a new one.";
    const calls = mockApi({ "POST /api/runs/r1/step": new Response(JSON.stringify({ detail: gone }), { status: 404 }) });
    const { result } = renderHook(() => useStepLoop("r1", start, () => {}));
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(calls).toHaveLength(1);
    expect(result.current.error).toBe(gone);
    expect(result.current.running).toBe(false);
  });

  // Ruling 12 (Plan 4 Task 4 fix round 1): this replaces Plan 3's "a 503 stops the loop". The server now backs
  // off on an outage (Ruling 5), and a stopped loop left a running run that Re-run live refused (409). The test
  // still pins the sentence, the Retry-After wait and that no call is made early; only the stop became a resume.
  it("a 503 waits for Retry-After, shows the sentence, then resumes", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const down = "Model calls are failing right now; the run resumes when they return.";
    let n = 0;
    const calls = mockApi({
      "POST /api/runs/r1/step": () =>
        ++n === 1
          ? new Response(JSON.stringify({ detail: down }), { status: 503, headers: { "Retry-After": "60" } })
          : { run: fixtures.run, answered },
    });
    const { result } = renderHook(() => {
      const [d, setD] = useState<RunRowsOut | null>(start);
      return useStepLoop("r1", d, setD);
    });
    await act(() => vi.advanceTimersByTimeAsync(59_000));
    expect(calls).toHaveLength(1);
    expect(result.current.error).toBe(down);
    expect(result.current.running).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(calls).toHaveLength(2);
    expect(result.current.error).toBeNull();
    expect(result.current.running).toBe(false);
  });

  it("a 503 without Retry-After waits 60 s, then resumes", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    let n = 0;
    const calls = mockApi({
      "POST /api/runs/r1/step": () =>
        ++n === 1 ? new Response(JSON.stringify({ detail: "Model calls are off right now." }), { status: 503 }) : { run: fixtures.run, answered },
    });
    const { result } = renderHook(() => {
      const [d, setD] = useState<RunRowsOut | null>(start);
      return useStepLoop("r1", d, setD);
    });
    await act(() => vi.advanceTimersByTimeAsync(59_000));
    expect(calls).toHaveLength(1);
    expect(result.current.running).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(calls).toHaveLength(2);
  });

  it("any other error stops the loop", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const calls = mockApi({ "POST /api/runs/r1/step": new Response("{}", { status: 500 }) });
    const { result } = renderHook(() => useStepLoop("r1", start, () => {}));
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(calls).toHaveLength(1);
    expect(result.current.error).toBe("Request failed (500)");
    expect(result.current.running).toBe(false);
  });

  it("stops calling once unmounted", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const calls = mockApi({ "POST /api/runs/r1/step": { run: running, answered: [] } });
    const { unmount } = renderHook(() => useStepLoop("r1", start, () => {}));
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(calls).toHaveLength(1);
  });
});
