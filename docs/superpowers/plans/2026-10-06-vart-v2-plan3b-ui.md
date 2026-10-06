# VART v2 - Plan 3B: The console UI, integration, E2E and release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build every view of VART's frontend in design direction C ("console") against the frozen HTTP contract, then merge the three Plan 3 lanes, prove the whole product with Playwright, and release it.

**Architecture:** The UI lane starts from Plan 3A's Part 0 (the frozen contract and the generated `web/src/lib/api-types.ts`) and first merges branch `design` (8393ed0: `design.md`, the `@theme` tokens in `web/src/index.css`, self-hosted JetBrains Mono, the mockups). Views are plain React components routed by query string (only `/` and `/api/*` exist in production); one typed client (`lib/api.ts`) wraps every endpoint with the generated types; one keyboard hook (`lib/keys.ts`) drives the key map in `design.md`. Tests stub `fetch` with typed fixtures (`src/test/mockApi.ts`), which is the mock API generated from the frozen contract: the fixtures only compile if they match `api-types.ts`. Integration merges the lanes on `plan3`, wires a record/replay switch into the API's model client for Playwright, records the E2E model calls once with the eval key, and releases through a pull request.

**Tech Stack:** React 19, Vite 8, TypeScript 6, Tailwind v4 (`@theme` tokens only), `@fontsource/jetbrains-mono` (self-hosted), Vitest 5 + Testing Library, Playwright 1.63, oxlint.

**Spec:** `docs/superpowers/specs/2026-10-03-vart-v2-design.md` sections 5, 6.12, 6.13, 8 (Tests), 9, 10, 11. Design system: `design.md` (merged from branch `design` in Task 1; binding for every view). Companion plan (contract, API, must-fixes, lanes 3A-inputs and 3A-runs): `docs/superpowers/plans/2026-10-06-vart-v2-plan3a-api.md`. Plan 6B (CSF gap check view, `VART-wt-csf/docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md` section 7) is written after this contract freezes and is not built here.

## Global Constraints

Plan 3A's Global Constraints apply to this file unchanged. The lines that matter most here, plus the design rules:

- Lane 3B-ui: worktree `~/Desktop/portfolio/projects/VART-wt-p3-ui`, branch `plan3-ui` from `plan3` after adversary checkpoint 1. Integration (Tasks 6-8): branch `plan3` in `~/Desktop/portfolio/projects/VART-wt-plan3`, database `vart_test_plan3`.
- Every commit message ends with exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never open, list, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/`.
- Tests never touch the network: Vitest stubs `fetch`; Playwright runs the API with recorded model replies (`LLM_MODE=replay`, Task 7). Recording uses only the eval key, by the lead, inside the command, never printed.
- Monochrome only: black, white and `neutral-*`, through the `design.md` tokens (`paper`, `sunken`, `mark`, `rule`, `rule-strong`, `ink`, `ink-2`, `ink-3`, `chrome`, `chrome-2`, `chrome-rule`, `on-chrome`, `on-chrome-2`). No hex, `rgb()` or `oklch()` under `web/src`. `python scripts/check_monochrome.py` is green before every commit.
- Frontend types come from the backend: import from `web/src/lib/api-types.ts` through `lib/api.ts`; never hand-write a request or response type. If a view needs a field the contract lacks, stop and ask the lead (a contract change needs a `docs/CONTRACTS.md` change-log line).
- `design.md` is binding: JetBrains Mono only (self-hosted, 400/500/700); three type sizes (`text-xs` 11px, `text-sm` 13px, `text-base` 14px); radius 0; no shadows; fixed heights (top bar 36px, list row 28px, section row and list header 24px, drawer header 32px, status line 28px, buttons 28px, filter toggles 24px); the keyboard map; key hints in `<kbd aria-hidden="true">` with `aria-keyshortcuts` on the control; labels in words with a fill or border as the second cue; motion only as listed.
- Decisions Tarun made (design branch, 2026-10-05): the Evidence drawer is full screen under 900px (a modal dialog that traps focus and returns it to the row); drafts read "Draft, not approved" everywhere (grid, drawer, export); confidence shows "—" for "confirmed by you" and "not applicable"; fonts are self-hosted.
- Routing by query string only (`?view=run&run=<id>&item=<id>`): only `/` and `/api/*` exist in production (carry-over, foundation adversary M5).
- The frontend calls `GET /api/workspace` (`ensureWorkspace`) before any workspace-dependent endpoint (carry-over, `app/api/deps.py` docstring).
- Frontend chain, green before every commit: `cd web && npm run lint && npm test && npm run build` plus `python scripts/check_monochrome.py` from the repo root.
- Each task owns the files it lists. Two-failure rule; never weaken, skip or delete a test.

## Review Focus

1. **Keyboard use with focus in a text field.** Typing "approve" into the search box or an interview answer must never approve, filter or navigate; Esc must still close the drawer or clear the search. Pinned in Task 1 (`useKeys ignores single keys while a text field has focus`) and Task 3 (`typing in search does not toggle filters`).
2. **A narrow screen (320-899px).** Expect: no horizontal page scroll, the list scrolls inside its container, the drawer full screen as a modal dialog that traps Tab and returns focus to its row on Esc. Pinned in Task 4 (`under 900px the drawer is a modal that traps focus and returns it`) and Task 7's E2E at 375px.
3. **The step loop meets a 429 or a network error mid-run.** Expect: the loop stops, the grid keeps every row it has, the status line says why in words (`Error: ...`), and reopening the run resumes it (a running run restarts the loop on mount). Pinned in Task 3 (`a 429 stops the loop and says why`, `a running run resumes on mount`).
4. **A workspace that expired while the tab was open** (cookie replaced, old ids now 404). Expect: the ExpiredNotice with a "start again" action, never a blank screen or a raw JSON error. Pinned in Task 1 (`a 404 on a remembered run shows the expired notice`).
5. **A long or hostile cell** (a 2,000-character question, an answer text with markup, a file name with a redaction token `<PERSON>.docx`). Expect: one-line rows with ellipsis in the grid, the full text in the drawer, markup shown as text (React escapes it; no `dangerouslySetInnerHTML` anywhere), `<PERSON>` shown literally. Pinned in Task 3 (`hostile text renders as text`) and a lint rule in Task 1 (oxlint `react/no-danger`).

## Lane gates (run by the lead)

- Lane 3B-ui starts after plan3a adversary checkpoint 1, in parallel with lanes 3A-inputs and 3A-runs. Implementer and reviewer: Opus 5.5 (spec 11.2: Frontend is Opus; Tarun: Opus reviews the frontend tasks).
- Adversary checkpoint 3 (Fable 5.1) on `plan3..plan3-ui` before the merge in Task 6: accessibility (focus order, keyboard traps, screen-reader names), copy that overstates, anything that renders untrusted text unsafely, and every place the UI could disagree with the contract.
- Integration (Tasks 6-8) is the lead's, on `plan3`. Merging lanes is local and needs no approval. Recording the E2E calls uses the eval key (the lead, no approval under its $5 cap). Every outward step in Task 8 is marked **Tarun**.

## File Structure

```
design.md, design/mockups/*, web/src/index.css, web/src/main.tsx, web/package.json, web/package-lock.json
                                   MERGED from branch `design` (Task 1)
web/src/lib/api.ts                 REPLACE (Task 1)  typed client for every endpoint; ApiError.retryAfter
web/src/lib/route.ts               NEW (Task 1)      query-string routing
web/src/lib/keys.ts                NEW (Task 1)      useKeys: the design.md key map
web/src/lib/labels.ts              NEW (Task 1)      label words, chip classes, confidence and approval text
web/src/components/ui.tsx          NEW (Task 1)      Kbd, Button, LabelChip, ErrorLine
web/src/components/Shell.tsx       NEW (Task 1)      top bar, status line, key sheet, expired notice
web/src/App.tsx                    REPLACE (Task 1)  routes views inside the Shell
web/src/test/mockApi.ts            NEW (Task 1)      fetch stub + typed fixtures (the mock API)
web/src/views/Home.tsx             NEW (Task 2)
web/src/views/Workspace.tsx        NEW (Task 2)      documents panel, questionnaire panel, column mapper
web/src/components/StatusPanel.tsx MODIFY (Task 2)   restyled to the console tokens
web/src/views/RunGrid.tsx          NEW (Task 3)      filter line, list, step loop
web/src/views/EvidenceDrawer.tsx   NEW (Task 4)
web/src/views/Questions.tsx        NEW (Task 5)
web/src/views/Export.tsx           NEW (Task 5)
web/src/views/AuditLog.tsx         NEW (Task 5)
web/src/**/*.test.tsx              NEW (each task)   Vitest
scripts/check_monochrome.py, tests/test_check_monochrome.py   MODIFY (Task 6)
web/tsconfig.node.json             MODIFY (Task 6)   type-check playwright.config.ts and e2e/
app/settings.py, app/api/deps.py, tests/test_llm_mode.py      MODIFY/NEW (Task 7)  LLM_MODE record/replay for E2E
web/playwright.config.ts, web/e2e/*.spec.ts, web/e2e/helpers.ts, web/e2e/fixtures/*, web/e2e/recorded.jsonl
                                   NEW/MODIFY (Task 7)
.github/workflows/ci.yml, .gitleaks.toml                       MODIFY (Task 7)
docs/PROGRESS.md, CLAUDE.md, docs/superpowers/specs/2026-10-03-vart-v2-design.md, both Plan 3 files' Execution notes
                                   MODIFY (Task 8)
```

---

## Lane 3B-ui (worktree `VART-wt-p3-ui`, branch `plan3-ui`)

### Task 1: Merge the design system; shell, routing, keys, typed client, mock API

**Files:**
- Merge: branch `design` (8393ed0)
- Replace: `web/src/lib/api.ts`, `web/src/App.tsx`, `web/src/App.test.tsx`, `web/src/components/ErrorBoundary.tsx`
- Create: `web/src/lib/route.ts`, `web/src/lib/keys.ts`, `web/src/lib/labels.ts`, `web/src/components/ui.tsx`, `web/src/components/Shell.tsx`, `web/src/test/mockApi.ts`, `web/src/lib/route.test.ts`, `web/src/lib/keys.test.tsx`, `web/src/components/Shell.test.tsx`
- Modify: `web/src/lib/api.test.ts`, `web/.oxlintrc.json` (create if absent)

**Interfaces:**
- Consumes: `web/src/lib/api-types.ts` (Plan 3A Task 2), `design.md`.
- Produces:
  - `lib/api.ts`: types `Health, Workspace, DocumentOut, DocumentPatch, DocumentUpdated, Mapping, QuestionnaireOut, QuestionnaireDetail, RunOut, RunRow, RunRowsOut, StepOut, AnswerSummary, AnswerDetail, CitationOut, QuestionOut, AnswerQuestionOut, SuggestionOut, AuditEventOut, Label`; `class ApiError { status; retryAfter: number | null }`; `request<T>`, `errorMessage`, `messageOf`, `ensureWorkspace(): Promise<Workspace>`, `resetWorkspaceForTests()`, `getHealth()`, and `api` with: `documents()`, `uploadDocument(file)`, `loadSampleDocuments()`, `updateDocument(id, patch)`, `deleteDocument(id)`, `documentLines(id, from, to)`, `questionnaires()`, `uploadQuestionnaire(file)`, `loadSampleQuestionnaire(name)`, `confirmMapping(id, mapping)`, `questionnaire(id)`, `createRun(questionnaireId)`, `step(runId)`, `run(runId)`, `runAnswers(runId)`, `approveVerified(runId)`, `exportUrl(runId)`, `answer(id)`, `editAnswer(id, text)`, `approve(id)`, `notApplicable(id, reason)`, `questions(runId)`, `answerQuestion(id, text)`, `skipQuestion(id)`, `acceptSuggestion(id)`, `audit()`, `resetWorkspace()`.
  - `lib/route.ts`: `type View = "home" | "workspace" | "run" | "questions" | "export" | "audit"`; `type Route = { view: View; run?: string; item?: string; questionnaire?: string }`; `readRoute(search?: string): Route`; `href(r: Route): string`; `go(r: Route): void`; `useRoute(): Route`.
  - `lib/keys.ts`: `useKeys(map: Record<string, (e: KeyboardEvent) => void>, enabled?: boolean): void`; `inTextField(target: EventTarget | null): boolean`.
  - `lib/labels.ts`: `LABEL_WORD: Record<Label, string>`, `CHIP: Record<Label, string>`, `FILTER_KEY: Record<Label, string>`, `confidenceText(a: AnswerSummary): string`, `approvalText(approved: boolean): string` (`"Approved"` / `"Draft, not approved"`).
  - `components/ui.tsx`: `Kbd`, `Button({ k, label, primary?, quiet?, submit?, disabled?, busy?, busyLabel?, onClick?, shortcut? })`, `LabelChip({ label })`, `ErrorLine({ message })`.
  - `components/Shell.tsx`: `Shell({ mode, cursor, hints, children, expiresAt, runId })`, `ExpiredNotice()`, `KeySheet({ onClose })`, `type ViewProps = { workspace: Workspace; onGone: () => void }`, `goneOn404(e, onGone): string | null`, `resetAndReload()`, `KEY_TABLE`.
  - `test/mockApi.ts`: `mockApi(routes): string[]` (returns the list of `METHOD /path` calls), `fixtures` (typed `run`, `rows`, `detail`, `documents`, `questionnaire`, `questions`, `audit`).

- [ ] **Step 1: Merge `design` into the lane branch**

```bash
git merge --no-ff design -m "merge design: direction C (console), tokens, JetBrains Mono self-hosted, mockups" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd web && npm ci && npm run build && cd .. && python scripts/check_monochrome.py
```

Expected: the merge applies cleanly (the design branch touches only `design.md`, `design/mockups/`, `web/src/index.css`, `web/src/main.tsx`, `web/package.json`, `web/package-lock.json`); the build passes; monochrome reports 0 problems. `App.tsx` still uses `bg-neutral-100` and `rounded`; Step 6 replaces it.

- [ ] **Step 2: Write the failing tests**

`web/src/lib/route.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { href, readRoute } from "./route";

describe("route", () => {
  it("reads and writes the query string only", () => {
    expect(readRoute("?view=run&run=r1&item=i9")).toEqual({ view: "run", run: "r1", item: "i9" });
    expect(href({ view: "run", run: "r1" })).toBe("?view=run&run=r1");
  });

  it("falls back to home for an unknown view", () => {
    expect(readRoute("?view=../../etc")).toEqual({ view: "home" });
    expect(readRoute("")).toEqual({ view: "home" });
  });
});
```

`web/src/lib/keys.test.tsx`:

```tsx
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useKeys } from "./keys";

function Probe({ onA, onEsc }: { onA: () => void; onEsc: () => void }) {
  useKeys({ a: onA, Escape: onEsc });
  return <input aria-label="search" />;
}

describe("useKeys", () => {
  it("fires a single key on the page", () => {
    const onA = vi.fn();
    render(<Probe onA={onA} onEsc={() => {}} />);
    fireEvent.keyDown(document.body, { key: "a" });
    expect(onA).toHaveBeenCalledTimes(1);
  });

  it("ignores single keys while a text field has focus, but Esc always works", () => {
    const onA = vi.fn();
    const onEsc = vi.fn();
    const { getByLabelText } = render(<Probe onA={onA} onEsc={onEsc} />);
    const input = getByLabelText("search");
    input.focus();
    fireEvent.keyDown(input, { key: "a" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onA).not.toHaveBeenCalled();
    expect(onEsc).toHaveBeenCalledTimes(1);
  });

  it("is case sensitive and ignores modified keys", () => {
    const onA = vi.fn();
    render(<Probe onA={onA} onEsc={() => {}} />);
    fireEvent.keyDown(document.body, { key: "A" });
    fireEvent.keyDown(document.body, { key: "a", metaKey: true });
    expect(onA).not.toHaveBeenCalled();
  });
});
```

`web/src/components/Shell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { ExpiredNotice, Shell, goneOn404 } from "./Shell";

describe("Shell", () => {
  it("numbers the views, marks the current one and names its key", () => {
    window.history.replaceState(null, "", "?view=run&run=r1");
    render(<Shell mode="RUN" cursor="AC-04 · 4/60" hints={[["j/k", "move"]]} runId="r1" expiresAt={null}>x</Shell>);
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveTextContent("run");
    expect(current).toHaveAttribute("aria-keyshortcuts", "2");
    expect(screen.getByText("AC-04 · 4/60")).toBeInTheDocument();
  });

  it("opens the key sheet on ? and closes it on Esc", async () => {
    render(<Shell mode="RUN" cursor="" hints={[]} runId="r1" expiresAt={null}>x</Shell>);
    await userEvent.keyboard("?");
    expect(screen.getByRole("dialog", { name: "keys" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "keys" })).not.toBeInTheDocument();
  });

  it("a 404 on a remembered id means the workspace is gone; other errors are words", () => {
    const onGone = vi.fn();
    expect(goneOn404(new ApiError(404, "Not found."), onGone)).toBeNull();
    expect(onGone).toHaveBeenCalledTimes(1);
    expect(goneOn404(new ApiError(500, "Request failed (500)"), onGone)).toBe("Request failed (500)");
  });

  it("the expired notice offers a fresh start", () => {
    render(<ExpiredNotice />);
    expect(screen.getByRole("alert")).toHaveTextContent("This workspace has expired");
    expect(screen.getByRole("button", { name: "Start again" })).toBeInTheDocument();
  });
});
```

`web/src/App.test.tsx` (replace: the old one anchored on the placeholder intro copy this task removes, carry-over Task 6 line; Task 2 adds the Home cases):

```tsx
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
```

In `web/src/lib/api.test.ts`, the workspace fixture gains `expires_at` and one test is added:

```ts
  it("keeps Retry-After on a 429", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "budget" }), { status: 429, headers: { "Retry-After": "120" } })));
    await expect(request("/api/runs/r/step", { method: "POST" })).rejects.toMatchObject({ status: 429, retryAfter: 120 });
  });
```

(and every `{ created_at: ... }` workspace body in that file becomes `{ created_at: "2026-10-03T12:00:00Z", expires_at: "2026-10-04T12:00:00Z" }`; the ApiError equality tests stay as they are: `retryAfter` is `null` on both sides).

- [ ] **Step 3: Run them to verify they fail**

Run: `cd web && npm test`
Expected: FAIL (`Cannot find module './route'`, `./keys`, `../test/mockApi`).

- [ ] **Step 4: Write `lib/api.ts`, `lib/route.ts`, `lib/keys.ts`, `lib/labels.ts`**

`web/src/lib/api.ts`:

```ts
import type { components } from "./api-types";

type S = components["schemas"];
export type Health = S["HealthOut"];
export type Workspace = S["WorkspaceOut"];
export type DocumentOut = S["DocumentOut"];
export type DocumentPatch = S["DocumentPatch"];
export type DocumentUpdated = S["DocumentUpdated"];
export type Mapping = S["Mapping"];
export type QuestionnaireOut = S["QuestionnaireOut"];
export type QuestionnaireDetail = S["QuestionnaireDetail"];
export type RunOut = S["RunOut"];
export type RunRow = S["RunRow"];
export type RunRowsOut = S["RunRowsOut"];
export type StepOut = S["StepOut"];
export type AnswerSummary = S["AnswerSummary"];
export type AnswerDetail = S["AnswerDetail"];
export type CitationOut = S["CitationOut"];
export type QuestionOut = S["QuestionOut"];
export type AnswerQuestionOut = S["AnswerQuestionOut"];
export type SuggestionOut = S["SuggestionOut"];
export type AuditEventOut = S["AuditEventOut"];
export type LinesOut = S["LinesOut"];
export type Label = AnswerSummary["label"];

export class ApiError extends Error {
  status: number;
  retryAfter: number | null;
  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${res.status})`;
}

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** `T` defaults to void for endpoints that answer 204 with no body. */
export async function request<T = void>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) {
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, await errorMessage(res), Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", body: form });
}

let workspace: Promise<Workspace> | undefined;

/** Test-only: forget the memoized workspace. */
export function resetWorkspaceForTests() {
  workspace = undefined;
}

/** Creates (or loads) this browser's workspace. Must resolve before any workspace call (app/api/deps.py). */
export function ensureWorkspace(): Promise<Workspace> {
  workspace ??= request<Workspace>("/api/workspace").catch((e) => {
    workspace = undefined;
    throw e;
  });
  return workspace;
}

/** Health answers 503 with a body when the database is down; both are readable states, not errors. */
export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { credentials: "same-origin" });
  if (res.status === 200 || res.status === 503) {
    const body = await res.clone().json().catch(() => undefined);
    if (body !== undefined) return body as Health;
  }
  throw new ApiError(res.status, await errorMessage(res));
}

const enc = encodeURIComponent;

export const api = {
  documents: () => request<DocumentOut[]>("/api/documents"),
  uploadDocument: (file: File) => upload<DocumentOut>("/api/documents", file),
  loadSampleDocuments: () => send<DocumentOut[]>("/api/documents/sample", "POST"),
  updateDocument: (id: string, patch: DocumentPatch) => send<DocumentUpdated>(`/api/documents/${enc(id)}`, "PATCH", patch),
  deleteDocument: (id: string) => send<void>(`/api/documents/${enc(id)}`, "DELETE"),
  documentLines: (id: string, from: number, to: number) =>
    request<LinesOut>(`/api/documents/${enc(id)}/lines?from=${from}&to=${to}`),
  questionnaires: () => request<QuestionnaireOut[]>("/api/questionnaires"),
  uploadQuestionnaire: (file: File) => upload<QuestionnaireOut>("/api/questionnaires", file),
  loadSampleQuestionnaire: (name: "vsq-a" | "mvsp-b") => send<QuestionnaireDetail>(`/api/questionnaires/sample/${name}`, "POST"),
  confirmMapping: (id: string, mapping: Mapping) => send<QuestionnaireDetail>(`/api/questionnaires/${enc(id)}/mapping`, "PUT", mapping),
  questionnaire: (id: string) => request<QuestionnaireDetail>(`/api/questionnaires/${enc(id)}`),
  createRun: (questionnaireId: string) => send<RunOut>(`/api/questionnaires/${enc(questionnaireId)}/runs`, "POST"),
  step: (runId: string) => send<StepOut>(`/api/runs/${enc(runId)}/step`, "POST"),
  run: (runId: string) => request<RunOut>(`/api/runs/${enc(runId)}`),
  runAnswers: (runId: string) => request<RunRowsOut>(`/api/runs/${enc(runId)}/answers`),
  approveVerified: (runId: string) => send<{ approved: number }>(`/api/runs/${enc(runId)}/approve-verified`, "POST"),
  exportUrl: (runId: string) => `/api/runs/${enc(runId)}/export`,
  answer: (id: string) => request<AnswerDetail>(`/api/answers/${enc(id)}`),
  editAnswer: (id: string, text: string) => send<AnswerSummary>(`/api/answers/${enc(id)}`, "PATCH", { text }),
  approve: (id: string) => send<AnswerSummary>(`/api/answers/${enc(id)}/approve`, "POST"),
  notApplicable: (id: string, reason: string) => send<AnswerSummary>(`/api/answers/${enc(id)}/not-applicable`, "POST", { reason }),
  questions: (runId: string) => request<QuestionOut[]>(`/api/runs/${enc(runId)}/questions`),
  answerQuestion: (id: string, text: string) => send<AnswerQuestionOut>(`/api/questions/${enc(id)}/answer`, "POST", { text }),
  skipQuestion: (id: string) => send<QuestionOut>(`/api/questions/${enc(id)}/skip`, "POST"),
  acceptSuggestion: (id: string) => send<AnswerSummary>(`/api/suggestions/${enc(id)}/accept`, "POST"),
  audit: () => request<AuditEventOut[]>("/api/audit"),
  resetWorkspace: () => send<void>("/api/workspace/reset", "POST"),
};
```

`web/src/lib/route.ts`:

```ts
import { useSyncExternalStore } from "react";

export type View = "home" | "workspace" | "run" | "questions" | "export" | "audit";
export type Route = { view: View; run?: string; item?: string; questionnaire?: string };

const VIEWS: readonly View[] = ["home", "workspace", "run", "questions", "export", "audit"];
const KEYS = ["run", "item", "questionnaire"] as const;

/** Only `/` and `/api/*` exist in production, so every view lives in the query string. */
export function readRoute(search: string = window.location.search): Route {
  const q = new URLSearchParams(search);
  const view = q.get("view") as View | null;
  const route: Route = { view: view && VIEWS.includes(view) ? view : "home" };
  if (route.view === "home") return route;
  for (const k of KEYS) {
    const v = q.get(k);
    if (v) route[k] = v;
  }
  return route;
}

export function href(r: Route): string {
  const q = new URLSearchParams({ view: r.view });
  for (const k of KEYS) if (r[k]) q.set(k, r[k] as string);
  return `?${q.toString()}`;
}

export function go(r: Route): void {
  window.history.pushState(null, "", href(r));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function subscribe(cb: () => void) {
  window.addEventListener("popstate", cb);
  return () => window.removeEventListener("popstate", cb);
}

export function useRoute(): Route {
  const search = useSyncExternalStore(subscribe, () => window.location.search);
  return readRoute(search);
}
```

`web/src/lib/keys.ts`:

```ts
import { useEffect, useRef } from "react";

/** True for inputs, textareas, selects and contenteditable: single keys there are typing, not commands. */
export function inTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** The design.md key map: single keys (case sensitive) fire only outside text fields; Escape always fires.
 * Keys pressed with Ctrl, Meta or Alt are left to the browser. */
export function useKeys(map: Record<string, (e: KeyboardEvent) => void>, enabled = true): void {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      if (e.key !== "Escape" && inTextField(e.target)) return;
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
```

`web/src/lib/labels.ts`:

```ts
import type { AnswerSummary, Label } from "./api";

export const LABEL_WORD: Record<Label, string> = {
  verified: "verified",
  partial: "partial",
  conflict: "CONFLICT",
  unknown: "unknown",
  user_confirmed: "confirmed by you",
  na: "not applicable",
};

/** design.md label chips: the word is always there; fill or border is the second cue. */
export const CHIP: Record<Label, string> = {
  verified: "bg-chrome text-on-chrome",
  user_confirmed: "bg-neutral-700 text-on-chrome",
  partial: "border border-ink text-ink",
  conflict: "border-2 border-ink font-bold uppercase text-ink",
  unknown: "border border-dashed border-neutral-400 text-ink-2",
  na: "text-ink-3",
};

/** design.md key map: v p c u y x toggle the filters. */
export const FILTER_KEY: Record<Label, string> = {
  verified: "v", partial: "p", conflict: "c", unknown: "u", user_confirmed: "y", na: "x",
};

export const LABELS: readonly Label[] = ["verified", "partial", "conflict", "unknown", "user_confirmed", "na"];

/** Tarun 2026-10-05: an em dash for answers no model scored. */
export function confidenceText(a: AnswerSummary): string {
  return a.label === "user_confirmed" || a.label === "na" ? "—" : a.confidence.toFixed(2);
}

export function approvalText(approved: boolean): string {
  return approved ? "Approved" : "Draft, not approved";
}
```

- [ ] **Step 5: Write `components/ui.tsx`, `components/Shell.tsx`, `test/mockApi.ts`**

`web/src/components/ui.tsx`:

```tsx
import type { ReactNode } from "react";
import type { Label } from "../lib/api";
import { CHIP, LABEL_WORD } from "../lib/labels";

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd aria-hidden="true">{children}</kbd>;
}

type ButtonProps = {
  k: string; // the key shown in the hint
  shortcut?: string; // aria-keyshortcuts when it differs from k ("Shift+A")
  label: string;
  onClick?: () => void;
  submit?: boolean; // a form's submit button: Enter in the form's fields presses it
  primary?: boolean;
  quiet?: boolean;
  disabled?: boolean;
  busy?: boolean;
  busyLabel?: string;
};

/** design.md: every action shows its key before the label; the accessible name is the label alone. */
export function Button({ k, shortcut, label, onClick, submit, primary, quiet, disabled, busy, busyLabel }: ButtonProps) {
  const look = quiet
    ? "text-on-chrome-2 hover:bg-chrome-2 hover:text-on-chrome"
    : primary
      ? "bg-chrome text-on-chrome hover:bg-neutral-800"
      : "border border-ink bg-paper text-ink hover:bg-sunken";
  return (
    <button
      type={submit ? "submit" : "button"}
      aria-keyshortcuts={shortcut ?? k}
      disabled={disabled || busy}
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-2 whitespace-nowrap px-2 text-sm font-medium active:translate-y-px disabled:cursor-not-allowed disabled:border-rule-strong disabled:bg-paper disabled:text-ink-3 ${look}`}
    >
      <Kbd>{k}</Kbd>
      <span>{busy ? (busyLabel ?? label) : label}</span>
    </button>
  );
}

export function LabelChip({ label }: { label: Label }) {
  return (
    <span className={`inline-block min-w-[9ch] px-1 text-center text-xs font-medium leading-[18px] ${CHIP[label]}`}>
      {LABEL_WORD[label]}
    </span>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return <p role="alert" className="text-xs font-medium text-ink">Error: {message}</p>;
}
```

`web/src/components/Shell.tsx`:

```tsx
import { useState, type ReactNode } from "react";
import { ApiError, api, messageOf, type Workspace } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go, href, useRoute, type View } from "../lib/route";
import { Button, Kbd } from "./ui";

const VIEWS: [View, string][] = [
  ["workspace", "workspace"],
  ["run", "run"],
  ["questions", "questions for you"],
  ["export", "export"],
  ["audit", "audit log"],
];

export const KEY_TABLE: [string, string][] = [
  ["s / o", "try with a sample company / use your own files (Home)"],
  ["1–5", "workspace · run · questions for you · export · audit log"],
  ["v p c u y x", "toggle a label filter (Run)"],
  ["/", "focus search"],
  ["j / k", "move down / up a row"],
  ["enter", "open the evidence drawer"],
  ["esc", "close the drawer or this sheet; clear search"],
  ["r", "re-run live"],
  ["e", "export"],
  ["A", "approve all verified"],
  ["i", "answer this question"],
  ["a", "approve"],
  ["n", "mark not applicable"],
  ["l / q / w", "load the sample documents / sample questionnaire A / B (Workspace)"],
  ["R", "reset the workspace: delete everything now (Workspace)"],
  ["ctrl+enter", "send an answer (Questions for you)"],
  ["?", "show all keys"],
];

function remaining(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `expires ${h}h${String(m).padStart(2, "0")}m`;
}

export function KeySheet({ onClose }: { onClose: () => void }) {
  return (
    <div role="dialog" aria-modal="true" aria-label="keys" className="fixed inset-0 z-20 overflow-auto bg-paper p-4">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center justify-between border-b border-ink pb-1">
          <h2 className="text-xs font-medium">all keys</h2>
          <Button k="esc" shortcut="Escape" label="Close" onClick={onClose} />
        </div>
        <table className="mt-2 w-full text-xs">
          <tbody>
            {KEY_TABLE.map(([k, what]) => (
              <tr key={k} className="border-b border-rule">
                <td className="w-32 py-1 font-medium">{k}</td>
                <td className="py-1 text-ink-2">{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export type ViewProps = { workspace: Workspace; onGone: () => void };

/** A 404 on an id the page remembered means the workspace changed under it (expired or reset). */
export function goneOn404(e: unknown, onGone: () => void): string | null {
  if (e instanceof ApiError && e.status === 404) {
    onGone();
    return null;
  }
  return messageOf(e);
}

export function ExpiredNotice() {
  useKeys({ Enter: () => window.location.assign("/") });
  return (
    <div role="alert" className="m-4 border border-rule-strong p-4">
      <p className="text-base font-medium">This workspace has expired or was reset.</p>
      <p className="mt-1 text-sm text-ink-2">Workspaces stop working after 24 hours. Start again to get a new one.</p>
      <div className="mt-3">
        <Button k="enter" shortcut="Enter" label="Start again" primary onClick={() => { window.location.assign("/"); }} />
      </div>
    </div>
  );
}

type ShellProps = {
  mode: string;
  cursor: string;
  hints: [string, string][];
  runId?: string;
  expiresAt: string | null;
  children: ReactNode;
};

/** design.md Workbench: inverted top bar (numbered views), the view, inverted status line. */
export function Shell({ mode, cursor, hints, runId, expiresAt, children }: ShellProps) {
  const route = useRoute();
  const [sheet, setSheet] = useState(false);
  const target = (v: View) => (v === "workspace" || v === "audit" ? { view: v } : runId ? { view: v, run: runId } : null);
  useKeys({
    "?": () => setSheet(true),
    Escape: () => setSheet(false),
    ...Object.fromEntries(
      VIEWS.map(([v], i) => [String(i + 1), () => { const t = target(v); if (t) go(t); }]),
    ),
  });
  const left = remaining(expiresAt);
  return (
    <div className="grid h-dvh grid-rows-[36px_minmax(0,1fr)_28px] bg-paper text-ink">
      <header data-chrome className="flex h-9 items-center gap-4 overflow-hidden bg-chrome px-4 text-on-chrome-2">
        <a href="/" className="font-bold tracking-[0.12em] text-on-chrome">VART</a>
        <nav aria-label="views" className="flex min-w-0 flex-1 gap-1 overflow-x-auto text-xs">
          {VIEWS.map(([v, name], i) => {
            const t = target(v);
            const current = route.view === v;
            return t ? (
              <a
                key={v}
                href={href(t)}
                onClick={(e) => { e.preventDefault(); go(t); }}
                aria-current={current ? "page" : undefined}
                aria-keyshortcuts={String(i + 1)}
                className={`flex h-6 items-center gap-1 whitespace-nowrap px-2 ${current ? "bg-on-chrome font-medium text-ink" : "hover:bg-chrome-2 hover:text-on-chrome"}`}
              >
                <Kbd>{i + 1}</Kbd> {name}
              </a>
            ) : (
              <span key={v} aria-disabled="true" className="flex h-6 items-center gap-1 whitespace-nowrap px-2 opacity-60">
                <Kbd>{i + 1}</Kbd> {name}
              </span>
            );
          })}
        </nav>
        {left && <span className="hidden text-xs min-[900px]:inline">{left}</span>}
      </header>
      <main className="min-h-0 overflow-auto">{children}</main>
      <footer data-chrome className="flex h-7 items-center gap-3 overflow-hidden bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="bg-on-chrome px-1 font-bold text-ink">{mode}</span>
        {cursor && <span>{cursor}</span>}
        {hints.map(([k, what], i) => (
          <span key={k} className={i > 1 ? "hidden min-[480px]:inline" : ""}><Kbd>{k}</Kbd> {what}</span>
        ))}
        <span className="ml-auto hidden min-[900px]:inline">VART · labels decided by code · synthetic demo data · MIT</span>
      </footer>
      {sheet && <KeySheet onClose={() => setSheet(false)} />}
    </div>
  );
}

/** Wipe now (POST /api/workspace/reset); the workspace view's `R` action calls this after a confirm. */
export async function resetAndReload() {
  await api.resetWorkspace();
  window.location.assign("/");
}
```

`web/src/test/mockApi.ts`:

```ts
import { vi } from "vitest";
import type {
  AnswerDetail, AuditEventOut, DocumentOut, Health, QuestionOut, QuestionnaireDetail, RunOut, RunRow, Workspace,
} from "../lib/api";

type Handler = unknown | Response | ((init: RequestInit | undefined, url: URL) => unknown | Response | Promise<unknown>);

/** The mock API: `"METHOD /path"` -> a typed body, a Response, or a function of the request. An unmocked call
 * answers 501 so a test fails loudly. Returns the list of calls made, in order. */
export function mockApi(routes: Record<string, Handler>): string[] {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      const key = `${init?.method ?? "GET"} ${url.pathname}`;
      calls.push(key);
      const h = routes[key];
      if (h === undefined) return new Response(JSON.stringify({ detail: `unmocked ${key}` }), { status: 501 });
      const out = typeof h === "function" ? await (h as (i?: RequestInit, u?: URL) => unknown)(init, url) : h;
      if (out instanceof Response) return out.clone();
      return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}

const item = (n: number, topic: string, question: string) => ({
  id: `i${n}`, position: n, row_ref: `Questionnaire!C${n + 6}`, code: `VSQ-${String(n).padStart(2, "0")}`,
  topic, question, csf_id: null,
});

const workspace: Workspace = { created_at: "2026-10-06T10:00:00Z", expires_at: "2026-10-07T10:00:00Z" };
const health: Health = { status: "ok", db: "ok", canary: null };
const run: RunOut = {
  id: "r1", questionnaire_id: "q1", status: "done", total: 3, done: 3, cost_usd: 0.002,
  models: { stance: "deepseek/deepseek-v4-pro" }, prompt_versions: { stance: "stance@p3" },
  started_at: "2026-10-06T10:01:00Z", finished_at: "2026-10-06T10:02:00Z",
};
const rows: RunRow[] = [
  {
    item: item(1, "Access Control", "Is user access reviewed at least quarterly?"),
    answer: { id: "a1", item_id: "i1", label: "conflict", value: null, text: "The policy says quarterly; the log shows reviews overdue. Which is current?", confidence: 0.3, sources: 2, approved: false, edited: false, statement_id: null },
  },
  {
    item: item(2, "Access Control", "Is MFA enforced for all workforce access?"),
    answer: { id: "a2", item_id: "i2", label: "verified", value: "Yes", text: "Yes. The access control policy requires MFA.", confidence: 0.9, sources: 1, approved: false, edited: false, statement_id: null },
  },
  { item: item(3, "Data Security", "Do customers manage their own keys?"), answer: null },
];
const detail: AnswerDetail = {
  ...rows[1].answer!, item: rows[1].item,
  citations: [{
    document_id: "d1", filename: "access-control-policy.docx", kind: "policy", status: "final", date: "2026-01-15",
    scope: null, line: 12, quote: "MFA is required for all workforce access.", stance: "yes", found_in_source: true,
    context: [
      { n: 11, text: "4. Authentication", cited: false },
      { n: 12, text: "MFA is required for all workforce access.", cited: true },
      { n: 13, text: "Exceptions need CISO approval.", cited: false },
    ],
  }],
  dropped: [{ reason: "placeholder", document_id: "d9", filename: "security-policy-template.md", line: 3, sentence: "This passage is unfilled template text." }],
  conflict: null, scope_note: null, statement_lines: [],
};
const documents: DocumentOut[] = [{
  id: "d1", filename: "access-control-policy.docx", source: "sample", kind: "policy", status: "final",
  effective_date: "2026-01-15", scope: null, evidence_allowed: true, metadata_source: "rule", line_count: 48,
  created_at: "2026-10-06T10:00:00Z",
}];
const questionnaire: QuestionnaireDetail = {
  id: "q1", filename: "v05.xlsx", source: "upload", format: "xlsx", sheets: ["Controls"],
  detected: { sheet: "Controls", header_row: 1, id_col: "A", question_col: "B", answer_col: "C", comments_col: "D", topic_col: null },
  mapping: null,
  preview: [{ row: 3, id: "VSQ-01", question: "Does your company run a documented security program?", topic: "GOVERNANCE", answer: null }],
  item_count: 0, latest_run_id: null, created_at: "2026-10-06T10:00:00Z", items: [],
};
const questions: QuestionOut[] = [{
  id: "qq1", run_id: "r1", item_ids: ["i3"], codes: ["VSQ-03"], reason: "unknown",
  text: "Do customers manage their own keys?", follow_up: null, status: "open", asked_count: 0, high_weight: true,
  suggestions: [],
}];
const audit: AuditEventOut[] = [{ at: "2026-10-06T10:02:00Z", actor: "visitor", action: "run.done", ref: "r1", detail: {} }];

export const fixtures = { workspace, health, run, rows, detail, documents, questionnaire, questions, audit };
```

The fixtures are typed by the generated `api-types.ts`: when the contract changes, `npm run build` fails here first.

- [ ] **Step 6: Replace `App.tsx`**

```tsx
import { useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import { ExpiredNotice } from "./components/Shell";
import { ErrorLine } from "./components/ui";
import { ensureWorkspace, messageOf, type Workspace } from "./lib/api";
import { useRoute } from "./lib/route";
import AuditLog from "./views/AuditLog";
import ExportView from "./views/Export";
import Home from "./views/Home";
import Questions from "./views/Questions";
import RunGrid from "./views/RunGrid";
import WorkspaceView from "./views/Workspace";

export default function App() {
  const route = useRoute();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    ensureWorkspace().then(setWorkspace, (e) => setError(messageOf(e)));
  }, []);

  const onGone = () => setGone(true);
  if (gone) return <ExpiredNotice />;
  if (route.view === "home" || !workspace) {
    return (
      <ErrorBoundary>
        <Home workspace={workspace} startError={error} />
      </ErrorBoundary>
    );
  }
  const props = { workspace, onGone };
  return (
    <ErrorBoundary>
      {route.view === "workspace" && <WorkspaceView {...props} />}
      {route.view === "run" && route.run && <RunGrid {...props} runId={route.run} itemId={route.item} />}
      {route.view === "questions" && route.run && <Questions {...props} runId={route.run} />}
      {route.view === "export" && route.run && <ExportView {...props} runId={route.run} />}
      {route.view === "audit" && <AuditLog {...props} />}
      {!route.run && ["run", "questions", "export"].includes(route.view) && <ErrorLine message="No run is selected; start one from the workspace." />}
    </ErrorBoundary>
  );
}
```

Until Tasks 2-5 land, create each view file as a one-line component so the build passes (`export default function RunGrid(_: unknown) { return null; }` and the same for the others); each task replaces its file. Restyle `ErrorBoundary.tsx` in this step (it used `rounded` and `bg-black`, which `design.md` replaces): the wrapper becomes `className="m-4 space-y-3 border border-rule-strong p-4"` and the button `className="h-7 bg-chrome px-2 text-sm font-medium text-on-chrome hover:bg-neutral-800"` (a class component cannot use `useKeys`, so it shows no key hint).

`web/.oxlintrc.json`:

```json
{ "rules": { "react/no-danger": "error" } }
```

- [ ] **Step 7: Run the tests and the gates**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS, and `npm run lint` reports no `react/no-danger`.

- [ ] **Step 8: Commit**

```bash
git add web/src web/.oxlintrc.json
git commit -m "feat(web): console shell, query-string routes, key map, typed client, mock API from the contract" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Home and Workspace (documents, questionnaire, column mapper)

**Files:**
- Replace: `web/src/views/Home.tsx`, `web/src/views/Workspace.tsx`, `web/src/components/StatusPanel.tsx`, `web/src/components/StatusPanel.test.tsx`
- Modify: `web/e2e/smoke.spec.ts` (new Home copy), `web/src/App.test.tsx` (the Home cases), `design.md` (key map change-log line)
- Test: `web/src/views/Home.test.tsx`, `web/src/views/Workspace.test.tsx`, `web/src/App.test.tsx`

**Interfaces:**
- Consumes: `api`, `ensureWorkspace`, `Shell`, `Button`, `ErrorLine`, `go`, `useKeys`, `goneOn404`, `ViewProps`.
- Produces: `Home({ workspace, startError })`; `WorkspaceView(props: ViewProps)`; `startSample(): Promise<string>` (exported from `Home.tsx`; resolves the run id); constants `NOTICE_URL = "https://github.com/Ttheegela/VART-v2/blob/main/data/NOTICE.md"`, `UPLOAD_NOTICE`.

Home (design.md Index-First, `design/mockups/home.html`): the wordmark bar with `synthetic demo data`; one `text-base` h1 "Questionnaires answered from your own documents"; one paragraph; the two ways in as rows with key hints (`s` try with a sample company, `o` use your own files); the "how a label is decided" table (label, when, value) in the mockup's words; the system status panel; the attribution line linking `data/NOTICE.md` (carry-over: CC BY-SA attribution reachable from the UI); the status line `HOME`. "Try with a sample company" loads the sample documents and `vsq-a`, creates a run and opens the run view; the run fills live (spec 5 step 4; Plan 4 precomputes it).

Workspace: a Documents panel (table: file, kind, status, date, scope, evidence, source, lines; an upload control accepting `.pdf,.docx,.xlsx,.csv,.md,.txt`; "Load the sample company's documents"; per row "Edit" opening a small form of selects and a date input, saved with PATCH, then "n answers decided again" in the status line; the upload notice) and a Questionnaire panel (upload `.xlsx,.csv`; sample buttons; the column mapper: sheet select, header row number, column selects A..last for question, answer, id, comments, topic; the preview table of 8 rows; Confirm; then the item count and `r` Start run). Every refusal shows under its control as `Error: <detail>`.

`UPLOAD_NOTICE` (triage row 30, spec 9): "Synthetic or public documents only. Uploads are redacted before they are stored or sent to a model (names, emails, phone numbers, street addresses and secrets), but a single first name or a name in lower case can slip through."

- [ ] **Step 1: Write the failing tests**

`web/src/views/Home.test.tsx`:

```tsx
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
});
```

`web/src/views/Workspace.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import WorkspaceView, { UPLOAD_NOTICE } from "./Workspace";

const props = { workspace: fixtures.workspace, onGone: () => {} };

describe("Workspace", () => {
  it("lists documents with their metadata in words and the upload notice", async () => {
    mockApi({ "GET /api/documents": fixtures.documents, "GET /api/questionnaires": [] });
    render(<WorkspaceView {...props} />);
    const row = await screen.findByRole("row", { name: /access-control-policy\.docx/ });
    expect(within(row).getByText("policy")).toBeInTheDocument();
    expect(within(row).getByText("evidence")).toBeInTheDocument();
    expect(screen.getByText(UPLOAD_NOTICE)).toBeInTheDocument();
  });

  it("shows a refused upload's sentence under the control", async () => {
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [],
      "POST /api/documents": new Response(JSON.stringify({ detail: "Files must be 4 MB or smaller." }), { status: 422 }),
    });
    render(<WorkspaceView {...props} />);
    const input = await screen.findByLabelText("upload documents");
    await userEvent.upload(input, new File(["x"], "big.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: Files must be 4 MB or smaller.");
  });

  it("previews the detected mapping, lets the visitor correct a column and confirm", async () => {
    let sent: unknown = null;
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [],
      "POST /api/questionnaires": fixtures.questionnaire,
      "PUT /api/questionnaires/q1/mapping": (init) => {
        sent = JSON.parse(String(init?.body));
        return { ...fixtures.questionnaire, mapping: sent, item_count: 20 };
      },
    });
    render(<WorkspaceView {...props} />);
    await userEvent.upload(await screen.findByLabelText("upload a questionnaire"), new File(["x"], "v05.xlsx"));
    expect(await screen.findByRole("cell", { name: /documented security program/ })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("comments column"), "D");
    await userEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(sent).toMatchObject({ sheet: "Controls", header_row: 1, question_col: "B", comments_col: "D" });
    expect(await screen.findByText("20 questions")).toBeInTheDocument();
  });

  it("an override reports how many answers were decided again", async () => {
    mockApi({
      "GET /api/documents": fixtures.documents,
      "GET /api/questionnaires": [],
      "PATCH /api/documents/d1": { ...fixtures.documents[0], status: "draft", metadata_source: "user", redecided: 3 },
    });
    render(<WorkspaceView {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit access-control-policy.docx" }));
    await userEvent.selectOptions(screen.getByLabelText("status"), "draft");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("3 answers decided again")).toBeInTheDocument();
  });
});
```

`web/src/App.test.tsx` (append inside the `describe`):

```tsx
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
```

(and `screen` joins the `@testing-library/react` import).

`StatusPanel.test.tsx`: update its expected text to the lowercase console copy (`overall`, `database`, `model check`, region name `system status`); the cases stay the same.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/views`
Expected: FAIL (the views are stubs).

- [ ] **Step 3: Write `views/Home.tsx`**

```tsx
import { useState } from "react";
import StatusPanel from "../components/StatusPanel";
import { Button, ErrorLine, Kbd } from "../components/ui";
import { api, ensureWorkspace, messageOf, type Workspace } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go } from "../lib/route";

export const NOTICE_URL = "https://github.com/Ttheegela/VART-v2/blob/main/data/NOTICE.md";

const HOW: [string, string, string][] = [
  ["verified", "Every surviving quote says the same thing, from a final document.", "Yes / No"],
  ["partial", "Mixed evidence, a negation in the quote, a scope difference, or draft documents only.", "Partial"],
  ["conflict", "Two documents disagree. A newer record is listed first, and you are asked which is current.", "—"],
  ["unknown", "No evidence survived the checks. The item goes to Questions for you.", "—"],
  ["confirmed by you", "You answered it; your answer is kept as a dated statement and cited.", "Yours"],
  ["not applicable", "You marked it so, with a reason in the audit log.", "N/A"],
];

/** Load the sample company's documents and questionnaire A, start a run; resolves the run id. */
export async function startSample(): Promise<string> {
  await ensureWorkspace();
  await api.loadSampleDocuments();
  const q = await api.loadSampleQuestionnaire("vsq-a");
  const run = await api.createRun(q.id);
  return run.id;
}

export default function Home({ workspace, startError }: { workspace: Workspace | null; startError: string | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sample = async () => {
    setBusy(true);
    setError(null);
    try {
      go({ view: "run", run: await startSample() });
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  };
  const own = () => go({ view: "workspace" });
  useKeys({ s: () => { if (!busy) void sample(); }, o: own });
  return (
    <div className="grid min-h-dvh grid-rows-[36px_1fr_28px] bg-paper text-ink">
      <header data-chrome className="flex h-9 items-center gap-4 bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="font-bold tracking-[0.12em] text-on-chrome">VART</span>
        <span>synthetic demo data</span>
      </header>
      <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
        <h1 className="text-base font-medium">Questionnaires answered from your own documents</h1>
        <p className="text-base text-ink-2">
          VART reads a company's policies, reports and records, answers each item of a vendor security
          questionnaire with the exact passage it came from, flags documents that disagree, and asks you only
          what the documents do not cover. Labels are decided by code, never by the model.
        </p>
        <ErrorLine message={startError ?? error} />
        <ul className="divide-y divide-rule border-y border-rule-strong">
          <li className="flex flex-wrap items-center gap-3 py-2">
            <Button k="s" label="Try with a sample company" primary busy={busy} busyLabel="Starting…" onClick={sample} disabled={!workspace} />
            <span className="min-w-0 text-sm text-ink-2 [overflow-wrap:anywhere]">
              Kestrelyn, a fictional SaaS company: 22 documents and the bundled Vendor Security Questionnaire.
            </span>
          </li>
          <li className="flex flex-wrap items-center gap-3 py-2">
            <Button k="o" label="Use your own files" onClick={own} disabled={!workspace} />
            <span className="min-w-0 text-sm text-ink-2 [overflow-wrap:anywhere]">
              An xlsx or csv questionnaire, plus documents in pdf, docx, xlsx, csv, md or txt. Your workspace is
              private and stops working after 24 hours.
            </span>
          </li>
        </ul>
        <section aria-label="how a label is decided">
          <h2 className="border-b border-ink text-xs font-medium text-ink-2">how a label is decided</h2>
          <table className="w-full text-sm">
            <thead className="text-xs text-ink-3"><tr><th className="text-left">label</th><th className="text-left">when</th><th className="text-left">value</th></tr></thead>
            <tbody>
              {HOW.map(([label, when, value]) => (
                <tr key={label} className="border-b border-rule align-top">
                  <td className="py-1 pr-3 font-medium">{label}</td>
                  <td className="py-1 pr-3 text-ink-2">{when}</td>
                  <td className="py-1">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <StatusPanel />
        <p className="text-xs text-ink-3">
          Sample policies adapted from JupiterOne security policy templates (CC BY-SA 4.0); questions informed by
          Google VSAQ (Apache-2.0) and MVSP (CC0). See the <a className="underline" href={NOTICE_URL}>data NOTICE</a>.
        </p>
      </main>
      <footer data-chrome className="flex h-7 items-center gap-3 bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="bg-on-chrome px-1 font-bold text-ink">HOME</span>
        <span><Kbd>s</Kbd> sample</span>
        <span><Kbd>o</Kbd> own files</span>
        <span className="hidden min-[480px]:inline"><Kbd>?</Kbd> all keys</span>
      </footer>
    </div>
  );
}
```

`StatusPanel.tsx`: same logic, console look: `<section aria-label="system status" className="border border-rule-strong">`, a `text-xs font-medium` heading `system status` with a 1px ink rule under it, and a `dl` of lowercase keys (`overall`, `database`, `model check`) in `text-ink-3` with the values in `ink`; the error line uses `ErrorLine`.

- [ ] **Step 4: Write `views/Workspace.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Shell, goneOn404, resetAndReload, type ViewProps } from "../components/Shell";
import { Button, ErrorLine } from "../components/ui";
import { api, type DocumentOut, type DocumentPatch, type Mapping, type QuestionnaireOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go } from "../lib/route";
import { NOTICE_URL } from "./Home";

export const UPLOAD_NOTICE =
  "Synthetic or public documents only. Uploads are redacted before they are stored or sent to a model (names, emails, phone numbers, street addresses and secrets), but a single first name or a name in lower case can slip through.";
const KINDS = ["policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other"] as const;
const SCOPES = ["internal-systems", "customer-product", "production", "employees", "vendors-and-contractors"] as const;
const COLUMNS = Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i));

function DocumentRow({ d, onSaved, onError }: { d: DocumentOut; onSaved: (n: number, d: DocumentOut) => void; onError: (m: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [patch, setPatch] = useState<DocumentPatch>({});
  const save = async () => {
    try {
      const out = await api.updateDocument(d.id, patch);
      setEditing(false);
      onSaved(out.redecided, out);
    } catch (e) {
      onError(String((e as Error).message));
    }
  };
  return (
    <>
      <tr className="h-7 border-b border-rule" aria-label={d.filename}>
        <td className="truncate pr-2">{d.filename}</td>
        <td>{d.kind}</td>
        <td>{d.status}</td>
        <td className="text-ink-3">{d.effective_date ?? "—"}</td>
        <td className="text-ink-3">{d.scope?.replace(/-/g, " ") ?? "—"}</td>
        <td>{d.evidence_allowed ? "evidence" : "not evidence"}</td>
        <td className="text-ink-3">{d.source}{d.metadata_source === "user" ? " · edited" : ""}</td>
        <td className="text-right tabular-nums">{d.line_count}</td>
        <td>
          <button type="button" aria-label={`Edit ${d.filename}`} className="text-xs underline" onClick={() => setEditing(!editing)}>edit</button>
        </td>
      </tr>
      {editing && (
        <tr className="border-b border-rule bg-sunken">
          <td colSpan={9} className="p-2">
            <form onSubmit={(e) => { e.preventDefault(); void save(); }} className="flex flex-wrap items-end gap-3 text-xs">
              <label className="flex flex-col">kind
                <select aria-label="kind" defaultValue={d.kind} onChange={(e) => setPatch({ ...patch, kind: e.target.value as DocumentPatch["kind"] })} className="h-7 border border-rule-strong bg-paper px-2 text-sm">
                  {KINDS.map((k) => <option key={k}>{k}</option>)}
                </select>
              </label>
              <label className="flex flex-col">status
                <select aria-label="status" defaultValue={d.status} onChange={(e) => setPatch({ ...patch, status: e.target.value as "final" | "draft" })} className="h-7 border border-rule-strong bg-paper px-2 text-sm">
                  <option>final</option><option>draft</option>
                </select>
              </label>
              <label className="flex flex-col">date
                <input type="date" defaultValue={d.effective_date ?? ""} onChange={(e) => setPatch({ ...patch, effective_date: e.target.value || null })} className="h-7 border border-rule-strong bg-paper px-2 text-sm" />
              </label>
              <label className="flex flex-col">scope
                <select aria-label="scope" defaultValue={d.scope ?? ""} onChange={(e) => setPatch({ ...patch, scope: (e.target.value || null) as DocumentPatch["scope"] })} className="h-7 border border-rule-strong bg-paper px-2 text-sm">
                  <option value="">none declared</option>
                  {SCOPES.map((s) => <option key={s} value={s}>{s.replace(/-/g, " ")}</option>)}
                </select>
              </label>
              <label className="flex items-center gap-1">
                <input type="checkbox" defaultChecked={d.evidence_allowed} onChange={(e) => setPatch({ ...patch, evidence_allowed: e.target.checked })} /> counts as evidence
              </label>
              <Button k="enter" shortcut="Enter" label="Save" primary submit />
            </form>
          </td>
        </tr>
      )}
    </>
  );
}

function Mapper({ q, onConfirmed }: { q: QuestionnaireOut; onConfirmed: (q: QuestionnaireOut) => void }) {
  const start = q.mapping ?? q.detected;
  const [m, setM] = useState<Mapping>(start ?? { sheet: q.sheets[0] ?? null, header_row: 1, id_col: null, question_col: "A", answer_col: "B", comments_col: null, topic_col: null });
  const [error, setError] = useState<string | null>(null);
  const col = (key: keyof Mapping, label: string, optional: boolean) => (
    <label className="flex flex-col text-xs">{label}
      <select aria-label={label} value={(m[key] as string | null) ?? ""} onChange={(e) => setM({ ...m, [key]: e.target.value || null })} className="h-7 border border-rule-strong bg-paper px-2 text-sm">
        {optional && <option value="">none</option>}
        {COLUMNS.map((c) => <option key={c}>{c}</option>)}
      </select>
    </label>
  );
  const confirm = async () => {
    try {
      onConfirmed(await api.confirmMapping(q.id, m));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="space-y-2">
      {!q.detected && <p className="text-sm text-ink-2">No question column was found; pick the columns below.</p>}
      <form onSubmit={(e) => { e.preventDefault(); void confirm(); }} className="flex flex-wrap items-end gap-3">
        {q.sheets.length > 0 && (
          <label className="flex flex-col text-xs">sheet
            <select aria-label="sheet" value={m.sheet ?? ""} onChange={(e) => setM({ ...m, sheet: e.target.value })} className="h-7 border border-rule-strong bg-paper px-2 text-sm">
              {q.sheets.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col text-xs">header row
          <input type="number" min={1} value={m.header_row} onChange={(e) => setM({ ...m, header_row: Number(e.target.value) || 1 })} className="h-7 w-20 border border-rule-strong bg-paper px-2 text-sm" />
        </label>
        {col("question_col", "question column", false)}
        {col("answer_col", "answer column", false)}
        {col("id_col", "id column", true)}
        {col("comments_col", "comments column", true)}
        {col("topic_col", "topic column", true)}
        <Button k="enter" shortcut="Enter" label="Confirm mapping" primary submit />
      </form>
      <ErrorLine message={error} />
      <table className="w-full table-fixed text-sm">
        <thead className="text-xs text-ink-3"><tr><th className="w-14 text-left">row</th><th className="w-24 text-left">id</th><th className="text-left">question</th><th className="w-40 text-left">topic</th></tr></thead>
        <tbody>
          {q.preview.map((p) => (
            <tr key={p.row} className="h-7 border-b border-rule">
              <td className="tabular-nums text-ink-3">{p.row}</td>
              <td className="truncate">{p.id ?? "—"}</td>
              <td className="truncate">{p.question}</td>
              <td className="truncate text-ink-3">{p.topic ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function WorkspaceView({ workspace, onGone }: ViewProps) {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [qs, setQs] = useState<QuestionnaireOut[]>([]);
  const [current, setCurrent] = useState<QuestionnaireOut | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [qError, setQError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.documents().then(setDocs, (e) => setDocError(goneOn404(e, onGone)));
    api.questionnaires().then((list) => { setQs(list); setCurrent(list[0] ?? null); }, (e) => setQError(goneOn404(e, onGone)));
  }, [onGone]);

  const uploadDocs = async (files: FileList | null) => {
    setDocError(null);
    for (const file of Array.from(files ?? [])) {
      try {
        const d = await api.uploadDocument(file);
        setDocs((all) => [...all, d]);
      } catch (e) {
        setDocError(`${file.name}: ${(e as Error).message}`);
      }
    }
  };
  const uploadQ = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setQError(null);
    try {
      const q = await api.uploadQuestionnaire(file);
      setQs((all) => [q, ...all]);
      setCurrent(q);
    } catch (e) {
      setQError((e as Error).message);
    }
  };
  const sampleDocs = async () => {
    setBusy(true);
    try { setDocs(await api.loadSampleDocuments().then(() => api.documents())); } catch (e) { setDocError((e as Error).message); }
    setBusy(false);
  };
  const sampleQ = async (name: "vsq-a" | "mvsp-b") => {
    try { const q = await api.loadSampleQuestionnaire(name); setQs((all) => [q, ...all]); setCurrent(q); } catch (e) { setQError((e as Error).message); }
  };
  const start = async () => {
    if (!current || current.item_count === 0) return;
    try { const run = await api.createRun(current.id); go({ view: "run", run: run.id }); } catch (e) { setQError((e as Error).message); }
  };
  const reset = () => {
    if (window.confirm("Delete this workspace and everything in it now?")) void resetAndReload();
  };
  useKeys({ r: () => void start(), l: () => void sampleDocs(), q: () => void sampleQ("vsq-a"), w: () => void sampleQ("mvsp-b"), R: reset });

  return (
    <Shell mode="WORKSPACE" cursor={note} hints={[["r", "start run"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={current?.latest_run_id ?? undefined}>
      <div className="space-y-6 p-4">
        <section aria-labelledby="docs-h" className="space-y-2">
          <h2 id="docs-h" className="border-b border-ink text-xs font-medium text-ink-2">documents ({docs.length})</h2>
          <p className="text-xs text-ink-3">{UPLOAD_NOTICE}</p>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm">
              <input aria-label="upload documents" type="file" multiple accept=".pdf,.docx,.xlsx,.csv,.md,.txt" onChange={(e) => void uploadDocs(e.target.files)} className="text-sm" />
            </label>
            <Button k="l" label="Load the sample company's documents" onClick={sampleDocs} busy={busy} busyLabel="Loading…" />
          </div>
          <ErrorLine message={docError} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[56rem] table-fixed text-sm">
              <thead className="text-xs font-medium text-ink-2"><tr className="h-6 border-b border-ink">
                <th className="text-left">file</th><th className="w-28 text-left">kind</th><th className="w-16 text-left">status</th><th className="w-28 text-left">date</th><th className="w-40 text-left">scope</th><th className="w-28 text-left">evidence</th><th className="w-28 text-left">source</th><th className="w-14 text-right">lines</th><th className="w-12" />
              </tr></thead>
              <tbody>
                {docs.map((d) => (
                  <DocumentRow key={d.id} d={d} onError={setDocError} onSaved={(n, out) => { setDocs((all) => all.map((x) => (x.id === out.id ? out : x))); setNote(`${n} answers decided again`); }} />
                ))}
              </tbody>
            </table>
          </div>
          {docs.some((d) => d.source === "sample") && (
            <p className="text-xs text-ink-3">Sample policies adapted from JupiterOne templates, CC BY-SA 4.0 (<a className="underline" href={NOTICE_URL}>NOTICE</a>).</p>
          )}
        </section>
        <section aria-labelledby="q-h" className="space-y-2">
          <h2 id="q-h" className="border-b border-ink text-xs font-medium text-ink-2">questionnaire</h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm">
              <input aria-label="upload a questionnaire" type="file" accept=".xlsx,.csv" onChange={(e) => void uploadQ(e.target.files)} className="text-sm" />
            </label>
            <Button k="q" label="Sample questionnaire A (xlsx)" onClick={() => void sampleQ("vsq-a")} />
            <Button k="w" label="Sample questionnaire B (csv)" onClick={() => void sampleQ("mvsp-b")} />
          </div>
          <ErrorLine message={qError} />
          {current && (
            <div className="space-y-2">
              <p className="text-sm">{current.filename} · <span>{current.item_count} questions</span></p>
              {current.item_count === 0 ? (
                <Mapper q={current} onConfirmed={(q) => { setCurrent(q); setQs((all) => all.map((x) => (x.id === q.id ? q : x))); }} />
              ) : (
                <Button k="r" label="Start run" primary onClick={() => void start()} />
              )}
            </div>
          )}
          {qs.length > 1 && <p className="text-xs text-ink-3">{qs.length} questionnaires in this workspace; the newest is shown.</p>}
        </section>
        <section aria-label="reset" className="border-t border-rule-strong pt-3">
          <Button k="R" shortcut="Shift+R" label="Reset workspace (delete everything now)" onClick={reset} />
        </section>
      </div>
    </Shell>
  );
}
```

The `l`, `q`, `w` and `R` keys are view-local additions to the design key map (already in `KEY_TABLE`, Task 1); add them to `design.md`'s keyboard table with a change-log line ("2026-10-06 · Workspace keys: l, q, w for the sample buttons, R resets the workspace after a confirm, r starts a run from the workspace").

`web/e2e/smoke.spec.ts`: the status panel is now `region` "system status" with lowercase keys; change the two locators to `status.locator('dt:text-is("overall") + dd')` and `dt:text-is("database")`, and the heading check to `page.getByText("VART").first()`.

- [ ] **Step 5: Run the tests and gates, commit**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS (including `App.test.tsx`'s Home case).

```bash
git add web/src design.md web/e2e/smoke.spec.ts
git commit -m "feat(web): home and workspace: sample start, uploads, metadata override, column mapper" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Run grid and the step loop

**Files:**
- Replace: `web/src/views/RunGrid.tsx`
- Test: `web/src/views/RunGrid.test.tsx`

**Interfaces:**
- Consumes: `api.runAnswers/step/createRun/approveVerified/exportUrl`, `Shell`, `LabelChip`, `Button`, `ErrorLine`, `useKeys`, `go`, labels, `goneOn404`, `EvidenceDrawer` (Task 4; a stub until then).
- Produces: `RunGrid({ workspace, onGone, runId, itemId })`; `useStepLoop(runId, initial: RunRowsOut | null, onRows): { error: string | null; running: boolean }`; `mergeRows(rows: RunRow[], answered: RunRow[]): RunRow[]`.

design.md "List row", "Filter line", "Command line": a `<table>` with `aria-rowcount`, sticky 24px header, 28px rows that never wrap, section rows `# topic`, the cursor column `>` (aria-hidden), roving tabindex, `aria-selected` on the selected row; pending rows in `ink-3` reading `answering…`; the filter line with one toggle per label (`aria-pressed`, the key, the chip, the count) and `/` search ("question text or ID"); the command line `<questionnaire> / run <n>` with `r` Re-run live, `e` Export, `A` Approve all verified (n). The step loop runs while `run.status === "running"`, merges each step's rows, stops on any error and shows it in words; mounting a running run starts the loop (resume).

- [ ] **Step 1: Write the failing tests**

`web/src/views/RunGrid.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import RunGrid, { mergeRows } from "./RunGrid";

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

  it("mergeRows replaces answered items in place", () => {
    const merged = mergeRows(fixtures.rows, [{ ...fixtures.rows[2], answer: fixtures.rows[1].answer }]);
    expect(merged.map((r) => r.answer?.id ?? null)).toEqual(["a1", "a2", "a2"]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/views/RunGrid.test.tsx`
Expected: FAIL (stub).

- [ ] **Step 3: Write `views/RunGrid.tsx`**

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, Kbd, LabelChip } from "../components/ui";
import { api, type Label, type RunRow, type RunRowsOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { FILTER_KEY, LABELS, approvalText, confidenceText } from "../lib/labels";
import { go } from "../lib/route";
import EvidenceDrawer from "./EvidenceDrawer";

export function mergeRows(rows: RunRow[], answered: RunRow[]): RunRow[] {
  const by = new Map(answered.map((r) => [r.item.id, r]));
  return rows.map((r) => by.get(r.item.id) ?? r);
}

/** Calls step while the run is running; stops on done or on any error (shown in words). */
export function useStepLoop(runId: string, data: RunRowsOut | null, onData: (d: RunRowsOut) => void) {
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const latest = useRef(data);
  latest.current = data;
  const status = data?.run.status;
  useEffect(() => {
    if (status !== "running") return;
    let alive = true;
    setRunning(true);
    setError(null);
    (async () => {
      while (alive) {
        try {
          const out = await api.step(runId);
          const cur = latest.current;
          if (!alive || !cur) return;
          const next = { run: out.run, rows: mergeRows(cur.rows, out.answered) };
          latest.current = next;
          onData(next);
          if (out.run.status !== "running") break;
        } catch (e) {
          if (alive) setError((e as Error).message);
          break;
        }
      }
      if (alive) setRunning(false);
    })();
    return () => { alive = false; };
  }, [runId, status, onData]);
  return { error, running };
}

export default function RunGrid({ workspace, onGone, runId, itemId }: ViewProps & { runId: string; itemId?: string }) {
  const [data, setData] = useState<RunRowsOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Set<Label>>(new Set());
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => {
    api.runAnswers(runId).then(setData, (e) => setLoadError(goneOn404(e, onGone)));
  }, [runId, onGone]);
  const { error: loopError, running } = useStepLoop(runId, data, setData);

  const counts = useMemo(() => {
    const c = Object.fromEntries(LABELS.map((l) => [l, 0])) as Record<Label, number>;
    for (const r of data?.rows ?? []) if (r.answer) c[r.answer.label] += 1;
    return c;
  }, [data]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.rows ?? []).filter((r) =>
      (filters.size === 0 || (r.answer && filters.has(r.answer.label))) &&
      (!q || r.item.question.toLowerCase().includes(q) || (r.item.code ?? "").toLowerCase().includes(q)));
  }, [data, filters, query]);
  const open = itemId ? visible.find((r) => r.item.id === itemId) : undefined;

  useEffect(() => { rowRefs.current[cursor]?.focus(); }, [cursor]);

  const toggle = (l: Label) => setFilters((f) => { const n = new Set(f); if (n.has(l)) n.delete(l); else n.add(l); return n; });
  const openRow = (i: number) => { const r = visible[i]; if (r?.answer) go({ view: "run", run: runId, item: r.item.id }); };
  const rerun = async () => {
    if (!data) return;
    setBusy("rerun");
    try { const run = await api.createRun(data.run.questionnaire_id); go({ view: "run", run: run.id }); } catch (e) { setActionError((e as Error).message); }
    setBusy(null);
  };
  const approveAll = async () => {
    setBusy("approve");
    try { await api.approveVerified(runId); setData(await api.runAnswers(runId)); } catch (e) { setActionError((e as Error).message); }
    setBusy(null);
  };
  const exportFile = () => { window.location.assign(api.exportUrl(runId)); };
  const verifiedOpen = (data?.rows ?? []).filter((r) => r.answer?.label === "verified" && !r.answer.approved).length;

  useKeys({
    ...Object.fromEntries(LABELS.map((l) => [FILTER_KEY[l], () => toggle(l)])),
    "/": () => search.current?.focus(),
    j: () => setCursor((c) => Math.min(c + 1, visible.length - 1)),
    ArrowDown: () => setCursor((c) => Math.min(c + 1, visible.length - 1)),
    k: () => setCursor((c) => Math.max(c - 1, 0)),
    ArrowUp: () => setCursor((c) => Math.max(c - 1, 0)),
    Enter: () => openRow(cursor),
    r: () => void rerun(),
    e: exportFile,
    A: () => void approveAll(),
  }, !open);

  const current = visible[cursor];
  let topic: string | null | undefined;
  return (
    <Shell
      mode="RUN"
      cursor={current ? `${current.item.code ?? current.item.position} · ${cursor + 1}/${visible.length}` : ""}
      hints={[["j/k", "move"], ["enter", "evidence"], ["/", "search"], ["?", "all keys"]]}
      expiresAt={workspace.expires_at}
      runId={runId}
    >
      <div className={`grid h-full min-h-0 ${open ? "min-[900px]:grid-cols-[minmax(0,1fr)_34rem]" : ""}`}>
        <div className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center gap-3 border-b border-rule-strong px-4 py-2">
            <div className="min-w-0">
              <h1 className="text-base font-medium">run <span className="text-ink-3">/</span> {runId.slice(0, 8)}</h1>
              <p className="text-xs text-ink-3">
                {data ? `${data.run.done} of ${data.run.total} answered · ${running ? "answering" : data.run.status} · $${data.run.cost_usd.toFixed(4)}` : "loading…"}
              </p>
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              <Button k="r" label="Re-run live" onClick={() => void rerun()} busy={busy === "rerun"} busyLabel="Starting…" disabled={running} />
              <Button k="e" label="Export" onClick={exportFile} disabled={!data} />
              <Button k="A" shortcut="Shift+A" label={`Approve all verified (${verifiedOpen})`} primary onClick={() => void approveAll()} busy={busy === "approve"} busyLabel="Approving…" disabled={verifiedOpen === 0} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-b border-rule-strong bg-sunken px-4 py-1">
            {LABELS.map((l) => (
              <button key={l} type="button" aria-pressed={filters.has(l)} aria-keyshortcuts={FILTER_KEY[l]} onClick={() => toggle(l)}
                className={`flex h-6 items-center gap-1 px-1 text-xs ${filters.has(l) ? "border border-ink bg-paper" : ""}`}>
                <Kbd>{FILTER_KEY[l]}</Kbd><LabelChip label={l} /><span className="font-bold tabular-nums">{counts[l]}</span>
              </button>
            ))}
            <label className="ml-auto flex items-center gap-1 text-xs">
              <Kbd>/</Kbd>
              <input ref={search} aria-label="search" placeholder="question text or ID" value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") { setQuery(""); e.currentTarget.blur(); } }}
                className="h-6 w-56 border border-rule-strong bg-paper px-2 text-sm placeholder:text-ink-3 hover:border-neutral-500" />
            </label>
          </div>
          <ErrorLine message={loadError ?? loopError ?? actionError} />
          <div className="min-h-0 flex-1 overflow-auto">
            <table aria-rowcount={visible.length} className="w-full min-w-[56rem] table-fixed text-sm">
              <thead className="sticky top-0 bg-paper text-xs font-medium text-ink-2">
                <tr className="h-6 border-b border-ink">
                  <th className="w-[2ch]" aria-label="cursor" /><th className="w-24 text-left">id</th><th className="w-36 text-left">label</th>
                  <th className="w-14 text-right">conf</th><th className="w-10 text-right">src</th><th className="text-left pl-3">question</th>
                  <th className="text-left">answer</th><th className="w-44 text-left">approval</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r, i) => {
                  const section = r.item.topic !== topic ? r.item.topic : undefined;
                  topic = r.item.topic;
                  const selected = r.item.id === itemId;
                  return [
                    section !== undefined && section !== null ? (
                      <tr key={`s-${r.item.id}`} className="h-6 border-b border-rule-strong text-xs text-ink-3"><td colSpan={8}># {section.toLowerCase()}</td></tr>
                    ) : null,
                    <tr
                      key={r.item.id}
                      ref={(el) => { rowRefs.current[i] = el; }}
                      tabIndex={i === cursor ? 0 : -1}
                      aria-selected={selected}
                      aria-label={`${r.item.code ?? r.item.position} ${r.item.question}`}
                      onClick={() => { setCursor(i); openRow(i); }}
                      className={`h-7 cursor-default border-b border-rule hover:bg-sunken ${selected ? "bg-sunken font-medium outline-2 -outline-offset-2 outline-ink" : ""} ${r.answer ? "" : "text-ink-3"}`}
                    >
                      <td aria-hidden="true">{i === cursor ? ">" : ""}</td>
                      <td className="truncate">{r.item.code ?? r.item.position}</td>
                      <td>{r.answer ? <LabelChip label={r.answer.label} /> : null}</td>
                      <td className="text-right tabular-nums">{r.answer ? confidenceText(r.answer) : ""}</td>
                      <td className="text-right tabular-nums">{r.answer ? r.answer.sources : ""}</td>
                      <td className="truncate pl-3">{r.item.question}</td>
                      <td className="truncate text-ink-2">{r.answer ? r.answer.text : "answering…"}</td>
                      <td className={`truncate ${r.answer?.approved ? "" : "text-ink-3"}`}>{r.answer ? approvalText(r.answer.approved) : ""}</td>
                    </tr>,
                  ];
                })}
              </tbody>
            </table>
          </div>
        </div>
        {open?.answer && (
          <EvidenceDrawer
            answerId={open.answer.id}
            code={open.item.code ?? String(open.item.position)}
            onClose={() => { go({ view: "run", run: runId }); rowRefs.current[cursor]?.focus(); }}
            onChanged={() => api.runAnswers(runId).then(setData)}
            runId={runId}
          />
        )}
      </div>
    </Shell>
  );
}

```

Until Task 4, `EvidenceDrawer.tsx` is a stub with the final props type: `export default function EvidenceDrawer(_: { answerId: string; code: string; runId: string; onClose: () => void; onChanged: () => void }) { return null; }`.

- [ ] **Step 4: Run the tests and gates, commit**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS.

```bash
git add web/src/views/RunGrid.tsx web/src/views/RunGrid.test.tsx web/src/views/EvidenceDrawer.tsx
git commit -m "feat(web): run grid with filter line, search, roving cursor and the resumable step loop" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Evidence drawer

**Files:**
- Replace: `web/src/views/EvidenceDrawer.tsx`
- Test: `web/src/views/EvidenceDrawer.test.tsx`

**Interfaces:**
- Consumes: `api.answer/approve/notApplicable`, `AnswerDetail`, `CitationOut`, `Button`, `LabelChip`, `ErrorLine`, `useKeys`, `go`, labels.
- Produces: `EvidenceDrawer({ answerId, code, runId, onClose, onChanged })`; `useNarrow(): boolean` (matchMedia `(max-width: 899px)`); `Citation({ c, n })`.

design.md "Inspector drawer", "Citation and line listing", "Conflict pair", "Dropped evidence": a right column of 34rem with a 1px ink left edge (not modal; the list stays usable) at 900px and wider; under 900px a full-screen `role="dialog" aria-modal="true"` that takes focus on open, traps Tab, and returns focus to the row on close (Tarun, 2026-10-05). Header on chrome: `<code> · evidence` and `esc close`. Body: the question (`text-base` 500), a key-value list (label, value, confidence, approval, rule), the answer in a `rule-strong` box with `[n]` footnotes, `sources (n)` with each citation as a `<figure>` (caption on `chrome-2`: `[n]` and the file in 700, then kind · status · date · scope · stance in on-chrome-2) and its numbered line listing (gutter `>` on the cited line, the quote in `<mark>`), `dropped evidence (n)` (reason in 700 uppercase, `file:line`, one sentence; dropped text never shown as a quote), the visitor's statement lines for "confirmed by you", then the actions: `a` Approve (disabled for conflict and unknown), `i` Answer this question (to the questions view), `n` Mark not applicable (asks for a reason inline). A citation whose `found_in_source` is false shows "quote not found in the stored source" in words (it should never happen; it is shown, never hidden).

- [ ] **Step 1: Write the failing tests**

`web/src/views/EvidenceDrawer.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import EvidenceDrawer from "./EvidenceDrawer";

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
      "POST /api/answers/a2/not-applicable": (init) => { body = JSON.parse(String(init?.body)); return { ...fixtures.rows[1].answer!, label: "na" }; },
    });
    render(<EvidenceDrawer {...base} onChanged={changed} onClose={() => {}} />);
    await screen.findByRole("figure", { name: /access-control/ });
    await userEvent.keyboard("n");
    await userEvent.type(screen.getByLabelText("reason"), "We take no card payments.{Enter}");
    expect(body).toEqual({ reason: "We take no card payments." });
    expect(changed).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/views/EvidenceDrawer.test.tsx`
Expected: FAIL (stub).

- [ ] **Step 3: Write `views/EvidenceDrawer.tsx`**

```tsx
import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Button, ErrorLine, LabelChip } from "../components/ui";
import { api, type AnswerDetail, type CitationOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { approvalText, confidenceText } from "../lib/labels";
import { go } from "../lib/route";

const NARROW = "(max-width: 899px)";

export function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => { const m = window.matchMedia(NARROW); m.addEventListener("change", cb); return () => m.removeEventListener("change", cb); },
    () => window.matchMedia(NARROW).matches,
  );
}

function quoted(text: string, quote: string) {
  const at = text.indexOf(quote);
  if (at < 0) return <>{text}</>;
  return <>{text.slice(0, at)}<mark className="bg-mark text-ink underline underline-offset-2">{quote}</mark>{text.slice(at + quote.length)}</>;
}

export function Citation({ c, n }: { c: CitationOut; n: number }) {
  const facts = [c.kind, c.status, c.date ?? "undated", c.scope?.replace(/-/g, " ") ?? "no scope declared", c.stance].join(" · ");
  return (
    <figure aria-label={`[${n}] ${c.filename}`} className="border border-rule-strong">
      <figcaption className="bg-chrome-2 px-2 py-1 text-xs text-on-chrome-2">
        <span className="font-bold text-on-chrome">[{n}] {c.filename}</span> <span>{facts}</span>
      </figcaption>
      {!c.found_in_source && <p className="px-2 py-1 text-xs font-medium">Quote not found in the stored source.</p>}
      <ol className="text-xs leading-[1.7]">
        {c.context.map((l) => (
          <li key={l.n} className={`grid grid-cols-[2ch_5ch_minmax(0,1fr)] ${l.cited ? "bg-sunken text-ink" : "text-ink-3"}`}>
            <span aria-hidden="true" className={l.cited ? "font-bold" : ""}>{l.cited ? ">" : ""}</span>
            <span className={`select-none border-r border-rule-strong pr-1 text-right tabular-nums ${l.cited ? "font-bold" : ""}`}>{l.n}</span>
            <span className="min-w-0 pl-2 [overflow-wrap:anywhere]">{l.cited ? quoted(l.text, c.quote) : l.text}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

type Props = { answerId: string; code: string; runId: string; onClose: () => void; onChanged: () => void };

export default function EvidenceDrawer({ answerId, code, runId, onClose, onChanged }: Props) {
  const narrow = useNarrow();
  const [a, setA] = useState<AnswerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const root = useRef<HTMLElement>(null);
  const titleId = `q-${answerId}`;

  useEffect(() => { api.answer(answerId).then(setA, (e) => setError((e as Error).message)); }, [answerId]);
  useEffect(() => { if (narrow && a) root.current?.querySelector<HTMLElement>("button")?.focus(); }, [narrow, a]);

  const approve = async () => { try { await api.approve(answerId); setA(await api.answer(answerId)); onChanged(); } catch (e) { setError((e as Error).message); } };
  const markNa = async () => { try { await api.notApplicable(answerId, reason); setAsking(false); setA(await api.answer(answerId)); onChanged(); } catch (e) { setError((e as Error).message); } };
  const canApprove = a !== null && a.label !== "conflict" && a.label !== "unknown" && !a.approved;
  useKeys({
    Escape: onClose,
    a: () => { if (canApprove) void approve(); },
    i: () => go({ view: "questions", run: runId, item: a?.item_id }),
    n: () => setAsking(true),
  });

  const trap = (e: ReactKeyboardEvent) => {
    if (!narrow || e.key !== "Tab" || !root.current) return;
    const items = Array.from(root.current.querySelectorAll<HTMLElement>("button:not([disabled]), input, textarea, select, a[href]"));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  const rule = a?.conflict ? (a.conflict.rule === "date" ? "date rule · newer record first" : "documents disagree") : a?.scope_note ? "scope difference" : "—";
  return (
    <aside
      ref={root}
      aria-labelledby={titleId}
      role={narrow ? "dialog" : undefined}
      aria-modal={narrow ? true : undefined}
      onKeyDown={trap}
      className={`${narrow ? "fixed inset-0 z-10" : "border-l border-ink"} flex min-h-0 flex-col overflow-auto bg-paper transition duration-200 ease-out`}
    >
      <div data-chrome className="flex h-8 items-center justify-between bg-chrome px-3 text-xs">
        <span className="font-bold text-on-chrome">{code} · evidence</span>
        <Button k="esc" shortcut="Escape" label="close" quiet onClick={onClose} />
      </div>
      <div className="space-y-4 p-3 text-sm">
        <ErrorLine message={error} />
        {a && (
          <>
            <h2 id={titleId} className="text-base font-medium">{a.item.question}</h2>
            <dl className="grid grid-cols-[11ch_minmax(0,1fr)] gap-y-1 text-sm">
              <dt className="text-ink-3">label</dt><dd><LabelChip label={a.label} /></dd>
              <dt className="text-ink-3">value</dt><dd>{a.value ?? "—"}</dd>
              <dt className="text-ink-3">confidence</dt><dd className="tabular-nums">{confidenceText(a)}</dd>
              <dt className="text-ink-3">approval</dt><dd className={a.approved ? "" : "text-ink-3"}>{approvalText(a.approved)}</dd>
              <dt className="text-ink-3">rule</dt><dd>{rule}</dd>
            </dl>
            <div className="border border-rule-strong p-2 text-ink-2 [overflow-wrap:anywhere]">{a.text || "No answer yet."}</div>
            {a.scope_note && <p className="text-ink-2">{a.scope_note}</p>}
            {a.statement_lines.length > 0 && (
              <section>
                <h3 className="border-b border-ink text-xs font-medium text-ink-2">your answer (dated statement)</h3>
                {a.statement_lines.map((l) => <p key={l.n} className="text-sm">{l.text}</p>)}
              </section>
            )}
            <section className="space-y-2">
              <h3 className="border-b border-ink text-xs font-medium text-ink-2">sources ({a.citations.length})</h3>
              {(a.conflict ? a.conflict.sides.flatMap((s) => s.citations) : a.citations.map((_, i) => i)).map((i) => (
                <Citation key={i} c={a.citations[i]} n={i + 1} />
              ))}
            </section>
            <section>
              <h3 className="border-b border-ink text-xs font-medium text-ink-2">dropped evidence ({a.dropped.length})</h3>
              <ul className="divide-y divide-rule">
                {a.dropped.map((d, i) => (
                  <li key={i} className="py-1 text-xs">
                    <span className="font-bold">{d.reason.replace(/-/g, " ").toUpperCase()}</span>{" "}
                    <span>{d.filename}{d.line ? `:${d.line}` : ""}</span>{" "}
                    <span className="text-ink-2">{d.sentence}</span>
                  </li>
                ))}
              </ul>
            </section>
            {asking && (
              <form onSubmit={(e) => { e.preventDefault(); if (reason.trim()) void markNa(); }} className="flex flex-wrap items-end gap-2">
                <label className="flex min-w-0 flex-1 flex-col text-xs">reason
                  <input autoFocus maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} className="h-7 border border-rule-strong bg-paper px-2 text-sm" />
                </label>
                <Button k="enter" shortcut="Enter" label="Mark not applicable" primary submit disabled={!reason.trim()} />
              </form>
            )}
            <div className="flex flex-wrap gap-2">
              <Button k="a" label="Approve" primary disabled={!canApprove} onClick={() => void approve()} />
              <Button k="i" label="Answer this question" onClick={() => go({ view: "questions", run: runId, item: a.item_id })} />
              <Button k="n" label="Mark not applicable" onClick={() => setAsking(true)} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
```

The dropped reason is upper-cased in the text itself (`PLACEHOLDER`, `NOT EVIDENCE`, `CONTAINMENT`, `INJECTION`, design.md), not by CSS, so screen readers and tests read the same word.

- [ ] **Step 4: Run the tests and gates, commit**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS.

```bash
git add web/src/views/EvidenceDrawer.tsx web/src/views/EvidenceDrawer.test.tsx
git commit -m "feat(web): evidence drawer with line listings, dropped evidence, conflict pair, full screen under 900px" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Questions for you, Export and Audit log

**Files:**
- Replace: `web/src/views/Questions.tsx`, `web/src/views/Export.tsx`, `web/src/views/AuditLog.tsx`
- Test: `web/src/views/Questions.test.tsx`, `web/src/views/Export.test.tsx`, `web/src/views/AuditLog.test.tsx`

**Interfaces:**
- Consumes: `api.questions/answerQuestion/skipQuestion/acceptSuggestion/runAnswers/exportUrl/audit`, `Shell`, `Button`, `ErrorLine`, `LabelChip`, `useKeys`, `useRoute`.
- Produces: `Questions({ workspace, onGone, runId })`, `ExportView({ workspace, onGone, runId })`, `AuditLog({ workspace, onGone })`.

Questions (spec 5 step 6, 6.9): the queue in the API's order (open and follow-up first), one row per question with its reason (`conflict`, `unknown`, `partial`), the question text, a textarea (at most 4,000 characters, a live count), `Enter` with Ctrl or Cmd to send, `s` skip; a follow-up replaces the prompt with the follow-up sentence; an accepted answer shows "confirmed by you" and lists the suggested fills with Accept buttons. With `?item=<id>` in the route, the matching question is focused first (from the drawer's `i`). Export (spec 5 step 7): approved vs draft counts, the line "Unapproved answers are exported marked "Draft, not approved".", the openpyxl notice for xlsx, and `e` Export (a link to `api.exportUrl`, `download`). Audit log: newest first, time, actor, action and ref; `/` filters by action.

- [ ] **Step 1: Write the failing tests**

`web/src/views/Questions.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import Questions from "./Questions";

const props = { workspace: fixtures.workspace, onGone: () => {}, runId: "r1" };

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
});
```

`web/src/views/Export.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import ExportView from "./Export";

describe("Export", () => {
  it("counts approved and draft answers and links the file", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<ExportView workspace={fixtures.workspace} onGone={() => {}} runId="r1" />);
    expect(await screen.findByText("0 approved · 2 draft · 1 unanswered")).toBeInTheDocument();
    expect(screen.getByText(/exported marked "Draft, not approved"/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export" })).toHaveAttribute("href", "/api/runs/r1/export");
  });
});
```

`web/src/views/AuditLog.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import AuditLog from "./AuditLog";

describe("AuditLog", () => {
  it("lists events newest first", async () => {
    mockApi({ "GET /api/audit": fixtures.audit });
    render(<AuditLog workspace={fixtures.workspace} onGone={() => {}} />);
    expect(await screen.findByRole("cell", { name: "run.done" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/views`
Expected: the three new files FAIL (stubs).

- [ ] **Step 3: Write `views/Questions.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, LabelChip } from "../components/ui";
import { api, type QuestionOut, type SuggestionOut } from "../lib/api";
import { useRoute } from "../lib/route";

const MAX = 4000;

function QuestionCard({ q, focus, onUpdated }: { q: QuestionOut; focus: boolean; onUpdated: (q: QuestionOut, fills: SuggestionOut[]) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fills, setFills] = useState<SuggestionOut[]>(q.suggestions);
  const box = useRef<HTMLTextAreaElement>(null);
  const code = q.codes[0] ?? "item";
  useEffect(() => { if (focus) box.current?.focus(); }, [focus]);
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api.answerQuestion(q.id, text);
      setText("");
      setFills(out.suggestions);
      onUpdated(out.question, out.suggestions);
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };
  const accept = async (s: SuggestionOut) => {
    try { await api.acceptSuggestion(s.id); setFills((all) => all.map((x) => (x.id === s.id ? { ...x, status: "accepted" } : x))); } catch (e) { setError((e as Error).message); }
  };
  const open = q.status === "open" || q.status === "follow_up";
  return (
    <li className="space-y-2 border-b border-rule py-3">
      <div className="flex flex-wrap items-baseline gap-2 text-sm">
        <span className="font-bold">{code}</span>
        <span className="text-xs uppercase text-ink-3">{q.reason}{q.high_weight ? " · high weight" : ""}</span>
        {q.status === "answered" && <LabelChip label="user_confirmed" />}
        {q.status === "skipped" && <span className="text-xs text-ink-3">skipped</span>}
      </div>
      <p className="text-base [overflow-wrap:anywhere]">{q.follow_up ?? q.text}</p>
      {open && (
        <div className="space-y-1">
          <textarea
            ref={box}
            aria-label={`your answer to ${code}`}
            maxLength={MAX}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim()) void send(); }}
            className="w-full border border-rule-strong bg-paper p-2 text-sm hover:border-neutral-500"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button k="ctrl+enter" shortcut="Control+Enter" label="Send" primary disabled={!text.trim()} busy={busy} busyLabel="Sending…" onClick={() => void send()} />
            <Button k="s" label="Skip" onClick={() => void api.skipQuestion(q.id).then((x) => onUpdated(x, []))} />
            <span className="ml-auto text-xs text-ink-3 tabular-nums">{text.length} / {MAX}</span>
          </div>
        </div>
      )}
      <ErrorLine message={error} />
      {fills.length > 0 && (
        <ul className="space-y-1 border-l border-ink pl-3 text-sm">
          {fills.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2">
              <span className="font-bold">{s.code}</span><LabelChip label={s.label} />
              <span className="min-w-0 flex-1 truncate text-ink-2">{s.question}</span>
              {s.status === "open" ? (
                <button type="button" aria-label={`Accept fill for ${s.code}`} onClick={() => void accept(s)} className="h-7 border border-ink px-2 text-sm hover:bg-sunken">accept</button>
              ) : (
                <span className="text-xs text-ink-3">{s.status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function Questions({ workspace, onGone, runId }: ViewProps & { runId: string }) {
  const route = useRoute();
  const [list, setList] = useState<QuestionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.questions(runId).then(setList, (e) => setError(goneOn404(e, onGone))); }, [runId, onGone]);
  const focusId = list?.find((q) => (route.item ? q.item_ids.includes(route.item) : q.status === "open"))?.id;
  const open = list?.filter((q) => q.status === "open" || q.status === "follow_up").length ?? 0;
  return (
    <Shell mode="ASK" cursor={`${open} open`} hints={[["ctrl+enter", "send"], ["s", "skip"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={runId}>
      <div className="mx-auto max-w-3xl p-4">
        <h1 className="border-b border-ink text-xs font-medium text-ink-2">questions for you ({open})</h1>
        <ErrorLine message={error} />
        {list && list.length === 0 && <p className="py-3 text-sm text-ink-2">Nothing to ask: every item has an answer from the documents, or the run is still filling.</p>}
        <ul>
          {list?.map((q) => (
            <QuestionCard key={q.id} q={q} focus={q.id === focusId} onUpdated={(nq) => setList((all) => all?.map((x) => (x.id === nq.id ? nq : x)) ?? null)} />
          ))}
        </ul>
      </div>
    </Shell>
  );
}
```

The skip button shows `s` and carries `aria-keyshortcuts="s"`, but no page-level key is bound: with several cards a single key would be ambiguous, and in the answer box it is typing. Change its hint to the plain label if the reviewer prefers no unbound hint (design.md: "the key does nothing" is only for disabled buttons).

- [ ] **Step 4: Write `views/Export.tsx` and `views/AuditLog.tsx`**

```tsx
// web/src/views/Export.tsx
import { useEffect, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { ErrorLine, Kbd } from "../components/ui";
import { api, type RunRowsOut } from "../lib/api";
import { useKeys } from "../lib/keys";

export default function ExportView({ workspace, onGone, runId }: ViewProps & { runId: string }) {
  const [data, setData] = useState<RunRowsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.runAnswers(runId).then(setData, (e) => setError(goneOn404(e, onGone))); }, [runId, onGone]);
  const url = api.exportUrl(runId);
  useKeys({ e: () => window.location.assign(url) });
  const rows = data?.rows ?? [];
  const approved = rows.filter((r) => r.answer?.approved).length;
  const draft = rows.filter((r) => r.answer && !r.answer.approved).length;
  const unanswered = rows.length - approved - draft;
  return (
    <Shell mode="EXPORT" cursor="" hints={[["e", "export"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={runId}>
      <div className="mx-auto max-w-3xl space-y-3 p-4 text-sm">
        <h1 className="border-b border-ink text-xs font-medium text-ink-2">export</h1>
        <ErrorLine message={error} />
        {data && <p className="tabular-nums">{approved} approved · {draft} draft · {unanswered} unanswered</p>}
        <p className="text-ink-2">
          The file you uploaded comes back with the answer column filled and three columns added: Status, Sources and
          Notes. Unapproved answers are exported marked "Draft, not approved". A csv comes back as csv.
        </p>
        <p className="text-xs text-ink-3">Embedded images and charts are not kept in an exported workbook (an openpyxl limit).</p>
        <a href={url} download aria-keyshortcuts="e" className="inline-flex h-7 items-center gap-2 bg-chrome px-2 text-sm font-medium text-on-chrome hover:bg-neutral-800">
          <Kbd>e</Kbd><span>Export</span>
        </a>
      </div>
    </Shell>
  );
}
```

```tsx
// web/src/views/AuditLog.tsx
import { useEffect, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { ErrorLine, Kbd } from "../components/ui";
import { api, type AuditEventOut } from "../lib/api";
import { useKeys } from "../lib/keys";

export default function AuditLog({ workspace, onGone }: ViewProps) {
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => { api.audit().then(setEvents, (e) => setError(goneOn404(e, onGone))); }, [onGone]);
  useKeys({ "/": () => search.current?.focus() });
  const shown = events.filter((e) => !query || e.action.includes(query.trim()));
  return (
    <Shell mode="AUDIT" cursor={`${shown.length} events`} hints={[["/", "search"], ["?", "all keys"]]} expiresAt={workspace.expires_at}>
      <div className="p-4">
        <div className="flex items-center gap-2 border-b border-ink pb-1">
          <h1 className="text-xs font-medium text-ink-2">audit log</h1>
          <label className="ml-auto flex items-center gap-1 text-xs"><Kbd>/</Kbd>
            <input ref={search} aria-label="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="action" className="h-6 w-48 border border-rule-strong bg-paper px-2 text-sm placeholder:text-ink-3" />
          </label>
        </div>
        <ErrorLine message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] table-fixed text-sm">
            <thead className="text-xs text-ink-2"><tr className="h-6"><th className="w-48 text-left">time</th><th className="w-20 text-left">actor</th><th className="w-56 text-left">action</th><th className="text-left">ref</th></tr></thead>
            <tbody>
              {shown.map((e, i) => (
                <tr key={i} className="h-7 border-b border-rule">
                  <td className="tabular-nums text-ink-3">{new Date(e.at).toISOString().replace("T", " ").slice(0, 19)} UTC</td>
                  <td>{e.actor}</td><td>{e.action}</td><td className="truncate text-ink-3">{e.ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
```

- [ ] **Step 5: Run the tests and gates, commit**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS.

```bash
git add web/src/views
git commit -m "feat(web): questions for you with follow-up and suggested fills, export, audit log" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Adversary checkpoint 3 for lane 3B-ui (lead dispatches Fable 5.1)** on `plan3..plan3-ui`; the lane fixes its findings before the merge.

---

## Integration (on `plan3`, the lead)

### Task 6: Merge the lanes; the monochrome gate's known misses; type-check the E2E files

**Files:**
- Merge: `plan3-inputs`, `plan3-runs`, `plan3-ui` into `plan3`
- Modify: `scripts/check_monochrome.py`, `tests/test_check_monochrome.py`, `web/tsconfig.node.json`
- Regenerate: `openapi.json`, `web/src/lib/api-types.ts`

**Interfaces:**
- Consumes: the three lanes.
- Produces: one `plan3` with every gate green; `scripts/check_monochrome.py` scanning declarations across lines and catching the six carried-over misses.

- [ ] **Step 1: Merge**

```bash
git merge --no-ff plan3-inputs -m "merge plan3-inputs: documents, import and mapper, re-decide, export, ingest must-fixes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git merge --no-ff plan3-runs -m "merge plan3-runs: step runner, answers, interview, audit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git merge --no-ff plan3-ui -m "merge plan3-ui: console UI in direction C" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python scripts/export_openapi.py && (cd web && npm run gen:api) && git diff --exit-code openapi.json web/src/lib/api-types.ts
```

Expected: no conflicts (disjoint files by construction; the only shared generated files are `openapi.json` and `api-types.ts`, where a conflict is resolved by regenerating them, never by hand). The final diff check is empty.

- [ ] **Step 2: Write the failing monochrome tests** (append to `tests/test_check_monochrome.py`)

```python
@pytest.mark.parametrize(
    "source",
    [
        "a {\n  color:\n    red;\n}\n",  # a value on the next line
        "a { box-shadow: 0 0 1px black, 0 0 2px red; }\n",  # a colour after a top-level comma (CSS)
        "<rect fill=red />\n",  # an unquoted HTML attribute
        "a { -webkit-text-stroke: 1px red; }\n",
        "a { text-emphasis: filled red; }\n",
        "a { color: LinkText; }\n",  # a system colour that is blue in every browser
        "a { background: Highlight; }\n",
        "a { accent-color: AccentColor; }\n",
    ],
)
def test_the_carried_over_misses_are_caught(tmp_path: Path, source: str) -> None:
    f = tmp_path / ("x.html" if source.startswith("<") else "x.css")
    f.write_text(source, encoding="utf-8")
    assert violations(f), source


def test_a_comma_in_a_js_style_object_still_ends_the_value(tmp_path: Path) -> None:
    f = tmp_path / "x.tsx"
    f.write_text('const s = { color: "black", outline: "none" };\n', encoding="utf-8")
    assert violations(f) == []


def test_the_design_tokens_pass(tmp_path: Path) -> None:
    f = tmp_path / "x.css"
    f.write_text("@theme { --color-mark: var(--color-neutral-200); }\nmark { background: var(--color-mark); }\n")
    assert violations(f) == []
```

Run: `pytest tests/test_check_monochrome.py -q`
Expected: the eight carried-over cases FAIL.

- [ ] **Step 3: Fix `scripts/check_monochrome.py`**

1. Add the coloured CSS system colours to the named list (they are not greys): after `GREYS`, `SYSTEM = "linktext visitedtext activetext highlight highlighttext accentcolor accentcolortext mark marktext selecteditem selecteditemtext".split()` and `_COLOURED = "|".join(sorted((set(CSS_COLOURS) - set(GREYS)) | set(SYSTEM)))`.
2. Extend `_PROPERTY` with the two text-decoration properties that take a colour: replace `(?:background|border|fill|stroke|outline|text-?decoration|caret|column-?rule)[\w-]*` by `(?:background|border|fill|stroke|outline|text-?decoration|text-?emphasis|caret|column-?rule|-webkit-text-stroke)[\w-]*`.
3. Values: `_VALUE` keeps its comma stop for scripts; CSS files get `_CSS_VALUE = r"(?:[^;}()]|\((?:[^()]|\([^()]*\))*\))*"` (commas and newlines inside, since a CSS declaration ends only at `;` or `}`). Both value patterns also allow a newline (`[^;,}()]` without `\n` in the class for CSS; for scripts keep `\n` excluded).
4. Attributes: the second `STYLE_VALUES` pattern's value alternation gains `|[^\s>"'{}]+` (unquoted).
5. Scan whole files for the style patterns: `violations()` runs `UTILITY`, `HEX`, `FUNCTION`, `EMOJI`, `FILTER` per line as today, and runs the style patterns once over the file text, reporting `text.count("\n", 0, match.start()) + 1` as the line. Choose the CSS or script value pattern by `path.suffix == ".css"`.

Run: `pytest tests/test_check_monochrome.py -q && python scripts/check_monochrome.py`
Expected: PASS; `monochrome: N files checked, 0 problems` on the real UI.

- [ ] **Step 4: Type-check the Playwright files** (carry-over Task 6 M7)

`web/tsconfig.node.json`: `"include": ["vite.config.ts", "playwright.config.ts", "e2e/**/*.ts"]`. Run `cd web && npm run build` (its `tsc -b` now checks them); fix any type error it reports in `e2e/` (none expected in `smoke.spec.ts`).

- [ ] **Step 5: All gates, commit**

Run: `ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check && python -m evals.run --pack dev && git diff --exit-code evals/results && (cd web && npm run lint && npm test && npm run build) && python scripts/check_monochrome.py`
Expected: every step green.

```bash
git add scripts/check_monochrome.py tests/test_check_monochrome.py web/tsconfig.node.json openapi.json web/src/lib/api-types.ts
git commit -m "ci: monochrome gate scans whole declarations and catches system colours; type-check e2e" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: Playwright E2E on recorded model replies (spec 8 "Tests")

**Files:**
- Modify: `app/settings.py`, `app/api/deps.py`, `web/playwright.config.ts`, `.github/workflows/ci.yml`, `.gitleaks.toml`
- Create: `tests/test_llm_mode.py`, `web/e2e/helpers.ts`, `web/e2e/sample.spec.ts`, `web/e2e/upload.spec.ts`, `web/e2e/export.spec.ts`, `web/e2e/interview.spec.ts`, `web/e2e/fixtures/backup-policy.md`, `web/e2e/recorded.jsonl` (written by the record run)

**Interfaces:**
- Consumes: `app.llm.recorder.ReplayClient/RecordingClient`, `OpenRouterClient`.
- Produces: `Settings.llm_mode: Literal["live", "record", "replay"] = "live"`, `Settings.llm_recording: str = ""`; `app.api.deps.get_llm()` honours them and refuses anything but `live` on Vercel.

The four flows spec 8 lists: the sample flow end to end; the upload flow with a messy xlsx; the export downloaded and checked cell by cell; the interview fills an item. The server answers model calls from `web/e2e/recorded.jsonl`; the lead records it once with the eval key. Prompts carry no ids or dates, so the keys are stable across days and machines; the E2E answers and the uploaded fixture contain no personal names, so redaction (spaCy spans can differ between macOS and Linux, final review I1) cannot change a key.

- [ ] **Step 1: Write the failing test** (`tests/test_llm_mode.py`)

```python
from pathlib import Path

import pytest

from app.api.deps import get_llm
from app.llm.recorder import ReplayClient


def test_replay_mode_serves_the_recording(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text("")
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_RECORDING", str(path))
    assert isinstance(get_llm(), ReplayClient)


def test_only_live_mode_runs_on_vercel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_RECORDING", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="live"):
        get_llm()


def test_live_mode_without_a_key_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert get_llm() is None
```

Run: `pytest tests/test_llm_mode.py -q` - Expected: FAIL (`get_llm` ignores `LLM_MODE`).

- [ ] **Step 2: Implement**

`app/settings.py` `Settings` gains (after `recheck_model`):

```python
    # E2E and local dev only: answer model calls from a recording (replay) or record them (record, eval key).
    llm_mode: Literal["live", "record", "replay"] = "live"
    llm_recording: str = ""
```

(`from typing import Literal`). `app/api/deps.py`:

```python
def get_llm() -> LLMClient | None:
    settings = get_settings()
    if settings.llm_mode == "live":
        return default_client()
    if os.environ.get("VERCEL") == "1":
        raise RuntimeError("LLM_MODE must be live on Vercel")
    path = Path(settings.llm_recording)
    if settings.llm_mode == "replay":
        return ReplayClient(path)
    live = default_client()
    return RecordingClient(live, path) if live is not None else None
```

(imports `from pathlib import Path`, `from app.llm.recorder import RecordingClient, ReplayClient`.)

Run: `pytest tests/test_llm_mode.py -q && pytest -q` - Expected: PASS.

- [ ] **Step 3: Point Playwright's server at the recording**

`web/playwright.config.ts`: the `webServer` block gains

```ts
        env: {
          LLM_MODE: process.env.LLM_MODE ?? "replay",
          LLM_RECORDING: process.env.LLM_RECORDING ?? fileURLToPath(new URL("./e2e/recorded.jsonl", import.meta.url)),
        },
```

(`import { fileURLToPath } from "node:url";`), and `timeout: 180_000` (the sample run ingests 22 documents and answers 64 items).

`.github/workflows/ci.yml` e2e job `env:` gains `LLM_MODE: replay` and `LLM_RECORDING: ${{ github.workspace }}/web/e2e/recorded.jsonl`.

`.gitleaks.toml`: the recordings allowlist's `paths` becomes `['''^(?:evals/recorded/[^/]+|web/e2e/recorded)\.jsonl$''']` (same rule, same 64-hex condition, so a real key inside a recorded prompt is still caught).

- [ ] **Step 4: Write the E2E tests**

`web/e2e/helpers.ts`:

```ts
import { execFileSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";

/** Start the sample company from Home and wait until the run is done; returns the run id. */
export async function sampleRun(page: Page): Promise<string> {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Try with a sample company" })).toBeEnabled();
  await page.keyboard.press("s");
  await page.waitForURL(/view=run&run=/);
  await expect(page.getByText(/64 of 64 answered · done/)).toBeVisible({ timeout: 150_000 });
  return new URL(page.url()).searchParams.get("run") as string;
}

/** Read cells of a downloaded xlsx with openpyxl (the repo's Python is on PATH in CI and locally). */
export function xlsxCells(path: string, sheet: string, cells: string[]): Record<string, unknown> {
  const script =
    "import json, sys, openpyxl\n" +
    "ws = openpyxl.load_workbook(sys.argv[1])[sys.argv[2]]\n" +
    "print(json.dumps({c: ws[c].value for c in sys.argv[3:]}, default=str))";
  return JSON.parse(execFileSync("python", ["-c", script, path, sheet, ...cells], { encoding: "utf-8" }));
}
```

`web/e2e/sample.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { sampleRun } from "./helpers";

test("the sample flow fills the questionnaire and opens the evidence", async ({ page }) => {
  await sampleRun(page);
  const rows = page.getByRole("row", { name: /^VSQ-\d\d / });
  await expect(rows).toHaveCount(64);
  await page.keyboard.press("v"); // the verified filter (the command line also has "Approve all verified")
  await rows.first().click();
  const drawer = page.getByRole("complementary");
  await expect(drawer.getByText(/^sources \(\d+\)$/)).toBeVisible();
  await expect(drawer.locator("mark").first()).toBeVisible();
  await expect(drawer.getByText("Draft, not approved")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("at 375px the page never scrolls sideways and the drawer is a modal", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await sampleRun(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("row", { name: /^VSQ-01 / }).click();
  await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
});
```

`web/e2e/upload.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const MESSY = fileURLToPath(new URL("../../data/mapper/v05.xlsx", import.meta.url));
const POLICY = fileURLToPath(new URL("./fixtures/backup-policy.md", import.meta.url));

test("a messy xlsx is mapped, confirmed and answered from an uploaded document", async ({ page }) => {
  await page.goto("/?view=workspace");
  await page.getByLabel("upload a questionnaire").setInputFiles(MESSY);
  await expect(page.getByRole("cell", { name: /information security program/ })).toBeVisible();
  await page.getByRole("button", { name: "Confirm mapping" }).click();
  await expect(page.getByText("20 questions")).toBeVisible();
  await page.getByLabel("upload documents").setInputFiles(POLICY);
  await expect(page.getByRole("row", { name: /backup-policy\.md/ })).toContainText("policy");
  await page.keyboard.press("r");
  await page.waitForURL(/view=run&run=/);
  await expect(page.getByText(/20 of 20 answered · done/)).toBeVisible({ timeout: 120_000 });
});
```

`web/e2e/fixtures/backup-policy.md` (no personal names, so redaction finds nothing):

```markdown
# Backup Policy

Scope: production

Customer data is backed up daily to a second region.

Backups are encrypted with AES-256 and restore tests run quarterly.
```

`web/e2e/export.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { sampleRun, xlsxCells } from "./helpers";

test("the export is the original workbook, filled, cell by cell", async ({ page }) => {
  await sampleRun(page);
  await page.keyboard.press("Shift+A");
  await expect(page.getByRole("button", { name: /Approve all verified \(0\)/ })).toBeDisabled();
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const file = await (await download).path();
  const cells = xlsxCells(file, "Questionnaire", ["A5", "C5", "F5", "G5", "H5", "A7", "C7", "D7", "F7", "G7"]);
  expect(cells).toMatchObject({ A5: "#", C5: "Control Question", F5: "Status", G5: "Sources", H5: "Notes", A7: "VSQ-01" });
  expect(cells.F7).toMatch(/^(Verified · Approved|(Partial|Conflict|Unknown) · Draft, not approved)$/);
  expect(["Yes", "No", "N/A", null]).toContain(cells.D7);
});
```

`web/e2e/interview.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { sampleRun } from "./helpers";

test("an answer in Questions for you fills its item", async ({ page }) => {
  const run = await sampleRun(page);
  await page.keyboard.press("3");
  await page.waitForURL(new RegExp(`view=questions&run=${run}`));
  const box = page.getByLabel(/^your answer to /).first();
  const code = (await box.getAttribute("aria-label"))!.replace("your answer to ", "");
  await box.fill("Yes. Customers can bring their own encryption keys, and keys are rotated every 90 days.");
  await page.getByRole("button", { name: "Send" }).first().click();
  const outcome = page.getByText(/also needs|^confirmed by you$/).first();
  await expect(outcome).toBeVisible();
  if ((await outcome.textContent())?.includes("also needs")) {
    await box.fill("The security team owns it and reviews it quarterly.");
    await page.getByRole("button", { name: "Send" }).first().click();
  }
  await expect(page.getByText("confirmed by you").first()).toBeVisible();
  await page.keyboard.press("2");
  await expect(page.getByRole("row", { name: new RegExp(`^${code} `) })).toContainText("confirmed by you");
});
```

- [ ] **Step 5: Record the E2E model calls once (lead, eval key)**

```bash
docker compose exec db createdb -U vart vart_test_e2e 2>/dev/null || true
export DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_e2e SESSION_SECRET=e2e-secret CRON_SECRET=e2e-cron
alembic upgrade head
cd web && rm -f e2e/recorded.jsonl && (set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" LLM_MODE=record npx playwright test)
```

Expected: every test passes live; `web/e2e/recorded.jsonl` holds the calls (a few cents of the eval key; stop and ask Tarun if the key's remaining credit is under $1). Then replay twice to prove determinism: `LLM_MODE=replay npx playwright test && LLM_MODE=replay npx playwright test` - Expected: PASS both times with no network (a `ReplayMiss` is a 500 from the step endpoint, which fails the test loudly).

Before committing, run gitleaks locally on the new file (`gitleaks dir --redact --no-banner web/e2e/recorded.jsonl` with the updated `.gitleaks.toml`; if gitleaks is not installed, Tarun runs `brew install gitleaks` first, as in the Plan 2 release).

- [ ] **Step 6: Commit**

```bash
git add app/settings.py app/api/deps.py tests/test_llm_mode.py web/playwright.config.ts web/e2e .github/workflows/ci.yml .gitleaks.toml
git commit -m "test(e2e): sample, messy upload, cell-by-cell export and interview flows on recorded model replies" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Docs, final review and the release (outward steps marked **Tarun**)

**Files:**
- Modify: `docs/PROGRESS.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-03-vart-v2-design.md`, both Plan 3 files (an "Execution notes" section each)
- Local (not in the repo): `~/Desktop/portfolio/projects/VART/.superpowers/sdd/later-plans-carryover.md`

- [ ] **Step 1: Update the docs (lead)**

- `docs/PROGRESS.md`: the Plan 3 row (`done` with the date), a "Plan 3" release block filled in Step 4, and decision rows: the HTTP contract frozen after checkpoint 1; the three Plan 3 lanes; the sample data ships in the function bundle from Plan 3 (spec 10 said Plan 4); csv originals are stored for export; documents a run used cannot be deleted; E2E answers model calls from `web/e2e/recorded.jsonl`.
- `CLAUDE.md` Map: add `app/api/` routers by lane, `app/runs.py` (step runner), `app/questions.py` (interview service), `app/questionnaires.py` (import and mapper), `app/export.py`, `app/redecide.py`; `web/src/views/`, `web/src/lib/{api,route,keys,labels}.ts`, `design.md` (binding for UI work); and under Commands: `cd web && npm run e2e` (replays `web/e2e/recorded.jsonl`; re-record with the Task 7 Step 5 command).
- Spec sync (each with "(Plan 3)"): 6.11 `questionnaires.original_bytes` keeps csv too; 6.12 adds `POST /api/documents/sample`, `GET /api/questionnaires`, `POST /api/answers/{id}/not-applicable`, `WorkspaceOut.expires_at`; 10 the sample data ships in the bundle from Plan 3; 8 the column-mapping gate is a pytest (`tests/test_questionnaires.py`), 10/10.
- `later-plans-carryover.md`: under Plan 4, the final review's non-must "Plan 3" rows this plan moved (9, 10, 12, 14, 15, 17, 19, 34, 47, 48, 50, 52), the name forms redaction still misses (single first names, lower case, "Ortiz Dana" when Presidio does not tag it) for SECURITY.md, and the precomputed sample run (replaying the dev recordings for `source = sample` runs is the cheapest way: Task 4 of plan3a keeps the order that needs).

Commit: `git commit -m "docs: Plan 3 progress, map, spec sync" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

- [ ] **Step 2: Final Opus review of `plan3`** (`5c7688b..plan3`, read-only, by area: the public surface, the release path, the cross-lane contract, trust boundaries). Fix findings on `plan3`; re-run every gate.

- [ ] **Step 3: Send Tarun one numbered release plan**

1. **Tarun:** `vercel deploy` (a preview, not `--prod`) from the `plan3` worktree. The lead reads the build output: the Python function size (Plan 2 was 70.91 MB; `data/dev/docs` and `data/questionnaires` add about 2 MB) and that `data/dev/docs/*.pdf`, `data/questionnaires/vsq-a.xlsx` and `python-multipart` are in the bundle.
2. **Tarun:** push `plan3` to `VART-v2` and open a pull request `plan3` -> `main`.
3. Wait for green CI on the pull request: gates (gitleaks over the full history with the new allowlist path, sponsor check, monochrome), backend (pytest, the dev eval replay with no drift, decide coverage), frontend (lint, Vitest, build, types drift), e2e (the four flows plus the smoke test on the recording). A `ReplayMiss` in e2e points at a prompt change since the recording: the lead re-records (Task 7 Step 5) and pushes.
4. **Tarun:** `ops/setup.sh migrate` from the `plan3` head (revision `3a1f0c9e7b21`: additive, two tables and four columns with constant defaults), so production reaches alembic head before any Plan 3 code deploys. Plan 2 code runs on the migrated schema, so a rollback needs no database step.
5. **Tarun:** fast-forward `main` to the pull request head and push (Vercel's Git integration deploys production).
6. Checks (lead, read-only): `python scripts/smoke.py https://vart-v2.vercel.app`; `/` serves the console Home; `/api/health` `"status":"ok"`; `/api/docs` lists the frozen operations. **Tarun:** one "Try with a sample company" run on production (spends about $0.04 of the production key; the precomputed path is Plan 4's) and one upload of `web/e2e/fixtures/backup-policy.md`, then "reset" the workspace.

Rollback: `vercel rollback` (no database step). After a rollback, Vercel stops auto-assigning the production domain to new Git deployments until the rollback is undone or a deployment is promoted (`vercel promote <url>`).

Push and release only on Tarun's OK.

- [ ] **Step 4: Record the release (lead)** in `docs/PROGRESS.md` (`main` sha, PR number, CI result, function size, migration, smoke, the production sample run's cost) through a docs-only pull request, as Plan 2 did.

---

## Self-review notes (for the lead)

- **Spec coverage.** 6.13 views (Home, Workspace with documents and the column mapper, Run grid, Evidence drawer, Questions for you, Export, Audit log), built first against the mock API typed from the contract (Tasks 1-5), then wired to the real API by the merge (Task 6); keyboard-usable grid and drawer; labels in words; monochrome (gate tightened in Task 6). Spec 8 "Tests": Vitest per view, Playwright's four flows (Task 7), the live smoke after deploy (Task 8). Spec 10's release order (migrate before `main` moves; check `/` and `/api/health`; preview bundle check) is Task 8 Step 3. design.md decisions Tarun made are Global Constraints.
- **Not built here (by design):** the precomputed sample run (spec 11.1 Plan 4), Google Drive import (Plan 5), the CSF gap check view (Plan 6B, which reuses `Shell`, `LabelChip`, `Citation` and the drawer), editing an answer's text in the UI (the endpoint exists; design.md gives it no key yet).
- **Type consistency.** Every view imports types from `lib/api.ts`, which re-exports `api-types.ts`; fixtures in `test/mockApi.ts` are typed by the same names, so a contract change fails `npm run build` before any test.
- **Placeholders.** None. View stubs in Task 1 are replaced by Tasks 2-5 within the lane, with their final props types written in Task 1.
