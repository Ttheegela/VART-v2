import type { AnswerSummary, GapLabel, GapScope, Label } from "./api";

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

/** Plan 4 Task 4: the only way a run ends `failed` is being closed after 10 minutes with no step. */
export const RUN_CLOSED = "This run was closed after 10 minutes without a step (for example, a closed tab). Press r to run again.";

export const LABELS: readonly Label[] = ["verified", "partial", "conflict", "unknown", "user_confirmed", "na"];

/** Tarun 2026-10-05: an em dash for answers no model scored. */
export function confidenceText(a: AnswerSummary): string {
  return a.label === "user_confirmed" || a.label === "na" ? "—" : a.confidence.toFixed(2);
}

export function approvalText(approved: boolean): string {
  return approved ? "Approved" : "Draft, not approved";
}

/** CSF spec 7: the gap labels in words; the chip's border or fill is the second cue (design.md Label chip). */
export const GAP_WORD: Record<GapLabel, string> = {
  covered: "covered",
  partly_covered: "partly",
  not_met: "not met",
  documents_disagree: "DISAGREE",
  gap: "gap",
  confirmed_by_you: "confirmed by you",
  not_answered: "not answered",
};

/** Ruling 14: an Ask-me answer is "answered by you"; "confirmed by you" is only a Checked outcome made Covered by fills. */
export const ANSWERED_WORD = "answered by you";

export const GAP_CHIP: Record<GapLabel, string> = {
  covered: "bg-chrome text-on-chrome",
  confirmed_by_you: "bg-neutral-700 text-on-chrome",
  partly_covered: "border border-ink text-ink",
  not_met: "border border-ink font-bold text-ink",
  documents_disagree: "border-2 border-ink font-bold uppercase text-ink",
  gap: "border border-dashed border-neutral-400 text-ink-2",
  not_answered: "text-ink-3",
};

export const GAP_LABELS: readonly GapLabel[] = [
  "covered", "partly_covered", "not_met", "documents_disagree", "gap", "confirmed_by_you", "not_answered",
];
export const SCOPES: readonly GapScope[] = ["govern", "identify", "protect", "detect", "respond", "recover", "core"];
/** CSF spec 7: g i p d s o for the functions (s: respond, since r runs), a for all of the core. */
export const SCOPE_KEY: Record<GapScope, string> = {
  govern: "g", identify: "i", protect: "p", detect: "d", respond: "s", recover: "o", core: "a",
};
export const GAP_REVIEW = "Possible gap — review it";
export const GAP_FOOTER = "Not legal advice. CSF 2.0 text © NIST, public domain.";
