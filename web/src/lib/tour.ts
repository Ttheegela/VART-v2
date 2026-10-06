import { useSyncExternalStore } from "react";
import type { Route } from "./route";

export type TourContext = { runId: string; conflictItem: string | null };
export type TourStep = { title: string; body: string; target: string; route: (c: TourContext) => Route | null };

/** Under 900 px the evidence drawer is a full-screen aria-modal dialog, so the tour never opens it there
 * (adversary-1 M9). jsdom has no matchMedia: wide. */
export const narrow = (): boolean => window.matchMedia?.("(max-width: 899px)").matches === true;

/** The guided tour in app order (Plan 4 Task 3b). `target` names the `data-tour` element outlined; `route` is where
 * the step shows (null: stay). Copy is for someone new to compliance: plain words, one idea a step. */
export const STEPS: TourStep[] = [
  {
    title: "What VART does",
    body: "Companies selling software get long security questionnaires from buyers. VART answers them from the company's own documents and shows where every answer came from.",
    target: "brand",
    route: () => null,
  },
  {
    title: "Your documents",
    body: "These are the sample company's policies, audit reports and spreadsheets. VART reads each one and notes what kind it is, whether it is final, and its date.",
    target: "documents",
    route: () => ({ view: "workspace" }),
  },
  {
    title: "The questionnaire",
    body: "This is the buyer's spreadsheet. VART finds the question and answer columns itself, and writes the answers back into the same file.",
    target: "questionnaire",
    route: () => ({ view: "workspace" }),
  },
  {
    title: "The answers",
    body: "Each row gets a label decided by code, not by the AI: verified (a quote backs it), partial, conflict (the documents disagree) or unknown (nothing found). The keys v, p, c and u filter by label; j and k move up and down.",
    target: "filters",
    route: (c) => ({ view: "run", run: c.runId }),
  },
  {
    title: "The evidence",
    body: "Every answer quotes the exact line it came from. When two documents disagree, both sides show with their dates, so a person decides which is current. Open any row to see its evidence.",
    target: "drawer",
    route: (c) =>
      c.conflictItem && !narrow() ? { view: "run", run: c.runId, item: c.conflictItem } : { view: "run", run: c.runId },
  },
  {
    title: "Questions for you",
    body: "What the documents do not cover is asked here, conflicts first. Your answer is saved as evidence and can fill other open questions too.",
    target: "questions",
    route: (c) => ({ view: "questions", run: c.runId }),
  },
  {
    title: "Export",
    body: "The answers go back into the buyer's own spreadsheet, with status, sources and notes. Answers nobody approved are marked as drafts.",
    target: "export",
    route: (c) => ({ view: "export", run: c.runId }),
  },
  {
    title: "Audit log",
    body: "Every upload, run, approval and edit in this workspace is listed here, so you can see what changed and when.",
    target: "audit",
    route: () => ({ view: "audit" }),
  },
  {
    title: "Gap check",
    body: "This checks the documents against NIST's Cybersecurity Framework 2.0, outcome by outcome; an outcome is one thing the framework asks a company to do. Press r to run it. For the untouched sample company it is precomputed; after your own answers or uploads it runs live. Open an outcome to see the smaller checks it is made of.",
    target: "coverage",
    route: () => ({ view: "gap" }),
  },
  {
    title: "Not legal advice",
    body: "VART flags possible gaps for a person to review. It is not an audit, a certification or legal advice, and this demo runs on made-up company data.",
    target: "legal",
    route: () => ({ view: "gap" }),
  },
];

type State = { open: boolean; step: number; ctx: TourContext | null };
let state: State = { open: false, step: 0, ctx: null };
let closedRun: string | null = null; // Skip or Done closes the tour for this run in this visit; no storage (Decision 17)
const listeners = new Set<() => void>();

function set(next: State): void {
  state = next;
  for (const l of listeners) l();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useTour(): State {
  return useSyncExternalStore(subscribe, () => state);
}

/** A view that moves focus on load (Questions for you) leaves it on the tour's Next while the tour is open. */
export const tourOpen = (): boolean => state.open;

export function startTour(ctx: TourContext): void {
  set({ open: true, step: 0, ctx });
}

/** Every time a precomputed sample run opens, unless the visitor closed the tour on that run in this visit. */
export function maybeStartTour(ctx: TourContext): void {
  if (!state.open && closedRun !== ctx.runId) startTour(ctx);
}

export function moveTour(by: number): void {
  if (!state.open) return;
  const step = state.step + by;
  if (step < 0) return;
  if (step >= STEPS.length) return stopTour();
  set({ ...state, step });
}

export function stopTour(): void {
  if (!state.open) return;
  closedRun = state.ctx?.runId ?? null;
  set({ ...state, open: false, step: 0 });
}

export function resetTourForTests(): void {
  closedRun = null;
  set({ open: false, step: 0, ctx: null });
}
