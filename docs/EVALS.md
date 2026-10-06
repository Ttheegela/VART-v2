# Evals

What is measured, how to run it, and what the committed results say. Every number below is copied from a file under
`evals/results/` (`latest.md`, `gap-dev.md`, `holdout.md`, `bench-draft.md`, `bench-stance.md`); those files are the
source, and CI fails when a replay differs from them.

## How to run each pack
Replay is the default: the whole pipeline runs over recorded model outputs, needs no network and no key, and rewrites
the results file (CI then fails on any `git diff` in `evals/results`).

| Pack | Replay (no key) | Writes |
|---|---|---|
| `dev` (the company the engine was built on, 2 questionnaires) | `python -m evals.run --pack dev` | `evals/results/latest.md` |
| `gap-dev` (the NIST CSF 2.0 gap check on the dev company) | `python -m evals.run --pack gap-dev` | `evals/results/gap-dev.md` |
| `holdout` (a second company, authored in parallel and first run after the tag `engine-freeze-plan4`) | `python -m evals.run --pack holdout` | `evals/results/holdout.md` |

Recording (`--mode record`, or `--mode live` without recording) and the model bench (`python -m evals.bench`) call
OpenRouter with the eval key from `~/.config/vart/eval.env` (a $5 credit limit), never the production key:

```
(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack dev --mode record)
```

## What each gate measures
A gate is the larger of the spec's value and the first real run's value minus 0.02, set after the baseline. The
holdout is reported, not tuned: only the seven spec-wide gates (citations, template or draft cited as verified,
injections followed, asked twice, answer checks, and the two redaction gates) gate it; the rest are reported with a
"below target" or "met target" note.

| Gate | What it measures | Target |
|---|---|---|
| classification_correct | document kind, status, date, scope and `evidence_allowed` against the fact sheet | >= 1.0 |
| retrieval_recall_at_8 | key evidence lines found in the top 8 passages (no pinned evidence) | >= 0.95 |
| label_accuracy | the answer's label against the key, before the interview | >= 0.9 |
| conflict_recall | planted conflict traps with at least one item labelled conflict | >= 1.0 |
| date_rule_correct | planted date traps resolved by the date rule | >= 1.0 |
| citations_valid | every cited quote re-read from the stored line | >= 1.0 |
| template_or_draft_cited_as_verified | template or draft evidence behind a verified label | <= 0.0 |
| injections_followed | planted injections that changed a target's label (definition below) | <= 0.0 |
| honest_negatives_kept | a real "No" kept as verified No | >= 1.0 |
| asked_twice | the same question asked of the visitor twice | <= 0.0 |
| fills_suggested | the interview's re-check suggests the fills the key expects | >= 1.0 |
| judge_faithfulness | a judge from a different model family finds the drafted answer faithful to its quotes | >= 0.95 |
| answer_checks_pass | the code checks on the answer text (names, numbers, quotes) | >= 1.0 |
| redaction_citations_valid, redaction_private_leaks | the same on redacted uploads: citations valid, private data never leaked | >= 1.0, <= 0.0 |

## Results
Models in the committed results: classify `deepseek/deepseek-v4-flash`, draft `z-ai/glm-5.3-flash`, judge
`qwen/qwen3.7-plus`, recheck and stance `deepseek/deepseek-v4-pro`.

| Gate | Target | Dev | Holdout |
|---|---|---|---|
| classification_correct | >= 1.0 | 1.0 | 0.8696 (below target) |
| retrieval_recall_at_8 | >= 0.95 | 0.9738 | 0.9781 |
| label_accuracy | >= 0.9 | 0.9326 | 0.8539 (below target) |
| conflict_recall | >= 1.0 | 1.0 | 0.7143 (below target) |
| date_rule_correct | >= 1.0 | 1.0 | 0.3333 (below target) |
| citations_valid | >= 1.0 | 1.0 | 1.0 |
| template_or_draft_cited_as_verified | <= 0.0 | 0.0 | 0.0 |
| injections_followed | <= 0.0 | 0.0 | 0.0 |
| honest_negatives_kept | >= 1.0 | 1.0 | 0.8571 (below target) |
| asked_twice | <= 0.0 | 0.0 | 0.0 |
| fills_suggested | >= 1.0 | 1.0 | 1.0 |
| judge_faithfulness | >= 0.95 | 0.971 | 0.973 |
| answer_checks_pass | >= 1.0 | 1.0 | 1.0 |
| redaction_citations_valid | >= 1.0 | 1.0 | 1.0 |
| redaction_private_leaks | <= 0.0 | 0.0 | 0.0 |

The dev pack passes 15 of 15 gates. The holdout passes its 7 gating gates and reports the other 8: 5 below target
(classification, label accuracy, conflict recall, date rule, honest negatives) and 3 that met it (retrieval, fills,
judge faithfulness). The misses are listed in
`evals/results/holdout.md` ("Label misses"); the answer keys' own disagreements and how each was decided are in
`data/holdout/key/RESOLUTIONS.md`. MVSP-2.4's key is Yes by derivation where a correct engine might say Partial
(RESOLUTIONS.md); it did not cost a miss in this run.

Reported, not gated:

| Metric | Dev | Holdout |
|---|---|---|
| ask_precision | 0.7027 | 0.6286 |
| ask_recall | 0.963 | 0.9167 |
| conflict_items_recall | 0.875 | 0.7273 |
| conflict_precision | 0.875 | 0.8889 |
| date_rule_items_correct | 0.75 | 0.5 |
| first_drafts_pass | 0.9565 | 1.0 |
| stance_accuracy | 0.9158 | 0.9333 |
| redaction_label_accuracy | 0.92 | 0.84 |
| scope_notes_on_scope_traps | 0.3333 | 0.3333 |
| fills_false | 0.0 | 2.0 |
| cost_usd_per_60_items | 0.0335 | 0.0594 |
| p50_seconds_per_item | 11.12 | 12.1 |

### gap-dev (the CSF 2.0 gap check)
| Gate | Target | Value |
|---|---|---|
| cited_coverage | >= 1.0 | 1.0 |
| trap_coverage | <= 0.0 | 0.0 |
| label_accuracy | >= 0.8 | 0.7097 (reported: below target, accepted 2026-10-06) |
| disagreements_caught | >= 1.0 | 1.0 |
| stated_noncompliance | >= 1.0 | 1.0 |
| nist_text_intact | >= 1.0 | 1.0 |
| honest_tiers | >= 1.0 | 1.0 |
| redaction_private_leaks | <= 0.0 | 0.0 |
| injections_followed | <= 0.0 | 0.0 |
| statements_as_evidence | <= 0.0 | 0.0 |

The gap check's label accuracy (22 of 31 outcomes) is reported below its 0.80 target. It was accepted on 2026-10-06
after two judged-key rounds and one tuning round; the nine misses and their causes (four retrieval, five stance) are
in `docs/PROGRESS.md`. Reported: part_agreement 0.7778, retrieval_recall_at_8 0.75, cost_usd_per_core_run 0.0378,
seconds_per_core_run 790.42.

## The holdout, and a definition that changed
The holdout company was authored in parallel and first run after the tag `engine-freeze-plan4`; its metrics are
reported, not tuned. Exactly one engine change landed after the tag: cf9d696 (adversary-2 M6), which makes the PDF inexact-page path fail closed and is likely unreachable; the dev, gap-dev and holdout replays are byte-identical after it, so nothing was re-recorded. One definition changed after its first score, and it is disclosed here:

- **First score.** `injections_followed` read 1.0 on the holdout (1 of 2 planted traps), so the gate failed.
- **Why it was wrong.** The old scorer counted any target item whose label differed from its key as an injection
  followed. The miss was VSQ-23: the stance model answered `yes` on "does not use customer payroll data to train
  machine learning models", and decide's negation rule capped the answer at Partial. The wiki injection tagged to
  that item was flagged at ingest and shown to no prompt of any item: the scorer counted a trap whose text never
  reached the model. It was an ordinary polarity miss.
- **New definition** (`evals/score.py` `target_followed`, also used by `evals/gap.py`). *Followed* means the target's
  label differs from the key AND the trap reached the target: a passage of that item (heading plus lines) shares a
  case-folded 5-word run with the injected text, or comes from the document that holds it (classify reads each
  document's first 40 lines). A citation that quotes the injection, or an answer that carries five of its words in a
  row, still counts, as before.
- **It fails closed.** When no stored line carries the injected text, the gate fails as "nothing to measure".
- **Before and after.** Holdout `injections_followed` 1.0 (1 of 2 traps) became 0.0 (0 of 2); the holdout's gating
  gates went from 6 of 7 to 7 of 7. Nothing was re-recorded and no prompt or model input changed; the dev
  (`latest.md`) and gap-dev results are byte-identical. VSQ-23 still counts in label_accuracy (0.8539) and
  honest_negatives_kept (0.8571).
- **Who decided.** Tarun chose the stricter definition with this disclosure (Ruling 13, 2026-10-07).

## Model bench and how the defaults were picked
`python -m evals.bench` makes live calls on the dev pack and writes `bench-stance.md` and `bench-draft.md` (not
reproduced in CI). For each step the pick is the cheapest pool model (cheap Chinese or open-weight OpenRouter models
with structured outputs) that passes every gate and scores within 0.02 of Claude Sonnet 5.5, the quality reference;
the draft pick is not the cheapest passing model (`openai/gpt-oss-120b` is cheaper) but has the highest judge faithfulness; Tarun approved the picks on 2026-10-05; stance's pick is 0.0225 below Sonnet 5.5's accuracy, outside the 0.02 rule,
and Tarun approved it. Stance: `deepseek/deepseek-v4-pro`. Draft: `z-ai/glm-5.3-flash`. Classify
stays `deepseek/deepseek-v4-flash` (not benched: the cheapest model that keeps classification at 22 of 22).

Stance (89 items):

| model | label_accuracy | conflicts_caught | failures | cost_usd | p50_seconds |
|---|---|---|---|---|---|
| deepseek/deepseek-v4-pro | 0.9438 | 7 | 0 | 0.0884 | 12.59 |
| anthropic/claude-sonnet-5.5 | 0.9663 | 7 | 0 | 0.7788 | 3.17 |
| qwen/qwen3.7-plus | 0.8764 | 7 | 0 | 0.0829 | 8.72 |
| z-ai/glm-5.3-flash | 0.8876 | 5 | 0 | 0.0326 | 3.79 |
| deepseek/deepseek-v4-flash | 0.8652 | 7 | 2 | 0.0199 | 6.77 |
| openai/gpt-oss-120b | 0.8315 | 6 | 2 | 0.0184 | 8.02 |
| moonshotai/kimi-k2.5 | 0.6966 | 4 | 12 | 0.137 | 8.48 |

Draft (72 items, judged by `qwen/qwen3.7-plus`):

| model | first_drafts_pass | judge_faithfulness | failures | cost_usd | p50_seconds |
|---|---|---|---|---|---|
| z-ai/glm-5.3-flash | 0.9722 | 0.9306 | 2 | 0.0284 | 1.83 |
| anthropic/claude-sonnet-5.5 | 0.9583 | 0.8611 | 2 | 0.2041 | 1.57 |
| openai/gpt-oss-120b | 0.9861 | 0.875 | 1 | 0.0139 | 1.58 |
| deepseek/deepseek-v4-flash | 0.9167 | 0.8889 | 4 | 0.0174 | 1.74 |
| deepseek/deepseek-v4-pro | 0.8194 | 0.8056 | 9 | 0.1126 | 3.83 |
| moonshotai/kimi-k2.5 | 0.6528 | 0.625 | 25 | 0.5242 | 14.06 |

`qwen/qwen3.5-flash-02-23` failed every call in both benches and `qwen/qwen3.7-plus` passed 0.0417 of drafts, so they
are left out of the tables above (the full rows are in the bench files).

## Cost and speed
- Per 60 items, replayed from the recordings: $0.0335 on the dev pack and $0.0594 on the holdout; p50 11.12 s and
  12.1 s per item.
- A live 64-item run after Plan 4's concurrent steps took 231 s in 16 steps and cost $0.0622, measured locally
  (FastAPI TestClient, live models), not on Vercel. The about 11 minutes (660 s) before is an estimate, 64 items x the
  10.35 s p50 run sequentially, not a measured run: about 3 times faster against that estimate.
- The end-to-end test makes 19 recorded model calls per pass, down from about 210.
- The sample run ("Try with a sample company") is copied from a precomputed snapshot and spends nothing.

## v1 against v2
The hackathon project (v1) scored label accuracy 0.515 and 0.545 before the interview on a private sponsor corpus,
caught 3 of 3 primary and 4 of 4 secondary conflicts, had 198 of 198 citations valid, and reached ask recall 0.81 and
precision 0.62. It is not like for like with v2's numbers above: the data differ (v1 used a sponsor's private pack, v2
uses public questionnaires and synthetic companies), and v1's retrieval inserted the answer key's evidence ahead of
the search results ("pinned evidence"), so its retrieval numbers flatter it. v2 pins nothing.
