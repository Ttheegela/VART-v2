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
