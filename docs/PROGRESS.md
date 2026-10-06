# VART v2 — Progress Log

_Last updated: 2026-10-06 · Branch: `main` (origin: https://github.com/Ttheegela/VART-v2, public) · Live: https://vart-v2.vercel.app_

## At a glance
| Plan | Status | Notes |
|---|---|---|
| 1A Foundation | done, live 2026-10-04 | schema, workspaces, LLM client, health + canary, React shell, CI, gates |
| 1B Dev data | done | fact sheet, questionnaires, documents, keys |
| 2 Engine and evals | done, live 2026-10-05 | engine, ingest, evals; baseline label accuracy 0.9213, recall@8 0.9738, cost $0.0361 per 60 items |
| 3 API and UI | done 2026-10-06 on `plan3`; release pending | 26 operations, step runner, column mapper, export, console UI, Playwright flows on recorded model replies |
| 6A CSF gap check, backend and evals | done; merged with Plan 3 on branch `plan6a`, release pending | gap-dev baseline: label accuracy 0.7097 (22 of 31; reported, below the 0.80 target, accepted 2026-10-06), 9 other gates pass; 6B (view, export, README, E2E) after Plan 3 |
| 6B CSF gap check, the visitor half | done on plan6b; release pending | Gap check view (tab 6), per-part runner and resume, check again per affected outcome, Ask-me answers filling Govern parts, gap sheet in both exports, the planted plan in the sample pack. Dev 15/15 with label_accuracy 0.9326; gap-dev 9/9 gating with label_accuracy 0.7097 reported; E2E 7/7, 210 model calls per pass; 1771 pytest and 131 vitest before this commit |
| 4 Hardening and launch | not started | |
| 5 Google Drive | not started | |

## Releases
### Plan 2 — 2026-10-05
- `main` = `c8836cc`, merged by PR #3 (fast-forward of `plan2`) after green CI: gates (gitleaks over the full history,
  sponsor check, monochrome), backend (1144 tests, decide at 100% branch coverage, the dev-pack eval replayed on Linux
  with no drift), frontend, e2e. Two CI jobs needed re-runs because GitHub assigned them no runner; no step had failed.
- Preview bundle check before the release: the Python function is 70.91 MB (READY on a CLI preview, region iad1).
- `ops/setup.sh migrate` (Tarun): Neon migrated `186f3400ded0` -> `ffbf91b464dc` (additive `chunks.record`) before
  `main` moved.
- Production deploy READY; smoke test ok (version `2.0.0.dev0`); `/api/health` `"status":"ok"`, `"db":"ok"`.
- Models now in production (set from the 2026-10-05 bench, approved by Tarun): stance and recheck
  `deepseek/deepseek-v4-pro`, draft `z-ai/glm-5.3-flash`, classify `deepseek/deepseek-v4-flash`, judge (evals only)
  `qwen/qwen3.7-plus`. The first canary on these ids is the 17:00 UTC run on 2026-10-06.
- Visitors cannot reach the engine or ingest yet: the questionnaire workspace arrives with Plan 3.

| Release check | Result |
|---|---|
| Dev pack (15 gates) | 15/15; label accuracy 0.9213, recall@8 0.9738, judge faithfulness 0.971 |
| Cost and speed | $0.0361 per 60 items; p50 10.35 s per item |
| Function size | 70.91 MB |
| Canary on the new models | pending: the 17:00 UTC run on 2026-10-06 |

### Plan 1 — 2026-10-04
- `main` = `f26ae27`, merged by PR #1 after green CI: backend 522 tests, frontend 18 tests, 1 e2e test, gates (gitleaks over
  the full history, sponsor check, monochrome).
- `ops/setup.sh release`: Neon migrated to `186f3400ded0`, fresh `CRON_SECRET`, Git connected (production branch `main`),
  production deployed; the smoke test, the canary (all three models ok) and `/api/health` (`"status":"ok"`) passed.
- Live: https://vart-v2.vercel.app (Vercel also assigned https://vart-orpin.vercel.app). The page shows the status panel;
  the questionnaire workspace arrives with Plans 2 and 3.
- Monitors (UptimeRobot, email alerts): HTTP on `/` every 5 min (served by the CDN, so the database stays asleep) and a
  keyword check for `"status":"ok"` on `/api/health` every 60 min.

| Release check | Result |
|---|---|
| Fluid compute | on (region iad1, next to Neon in us-east-1; default timeout 300 s) |
| Live canary | ok for all three models within the release script's 180 s limit; no `length` finish |
| Daily crons (cleanup 05:00 UTC, canary 17:00 UTC) | ok: `/api/health` at 19:58 UTC on 2026-10-05 showed `"status":"ok"` and the canary ok at 17:59 UTC that day (the canary cron ran; Hobby crons fire within their hour). The cleanup cron leaves no mark in `/api/health` |
| Vercel builds only `main` | ok: the push of this record's PR branch made no deployment (2026-10-04) |

### Plan 3
_Filled in after the release (Task 8 Step 4)._

## Decisions
This table is the decisions log kept in the repo. The detailed per-task review rulings are in the lead's local ledgers,
which are not in the repo; the ones that changed the spec or a plan are written into that document (the spec, and each
plan's "Execution notes").

| Date | Decision |
|---|---|
| 2026-10-03 | Stack copied from PriorPath v2; VART gets its own Vercel project and Neon project |
| 2026-10-03 | Unit contracts are frozen at the start of Plan 2, the HTTP contract at the start of Plan 3 (each with an adversary review); Plan 1 freezes only the shared text rules and data schemas |
| 2026-10-04 | Production domain `vart-v2.vercel.app` (`vart.vercel.app` was taken); a release goes through a PR with green CI, then `main` is fast-forwarded to it |
| 2026-10-04 | Monitors keep the demo alive without keeping Neon awake: `/` every 5 min, `/api/health` every 60 min |
| 2026-10-04 | Plan 2 models: every default comes from the model pool (cheap Chinese or open-weight OpenRouter models with structured outputs); Claude Sonnet 5.5 is only the bench's quality reference. A pick is the cheapest pool model that passes every gate and is within 0.02 of Sonnet 5.5, approved by Tarun; the starting defaults are Qwen and DeepSeek models (spec 6.14, 8) |
| 2026-10-04 | Plan 2 gates tighten after the baseline to max(spec value, baseline - 0.02) (spec 8) |
| 2026-10-04 | Redaction covers visitors' own interview answers too (names and emails become tokens), the same way as uploads (spec 9) |
| 2026-10-04 | Place names and cloud regions stay unredacted, because data-residency answers need them (spec 9) |
| 2026-10-04 | Presidio and spaCy `en_core_web_sm` ship in the Vercel function bundle; before the release the lead checks the function size on a `vercel deploy` preview, because Git previews are off for every branch except `main` (spec 10) |
| 2026-10-04 | Vectors are tried only if the real baseline's recall@8 is below 0.95, and kept only if they raise it by at least 0.05 (spec 6.5) |
| 2026-10-04 | Plan 2 runs three lanes in parallel, each in its own worktree: engine (Opus 5.5), ingest (Sonnet 5.5), evals (Sonnet 5.5) |
| 2026-10-04 | Eval key `VART_EVAL_OPENROUTER_API_KEY` lives in `~/.config/vart/eval.env` (mode 600, outside every repo, $5 credit limit); the lead, or an agent it names, runs recordings and the bench with it without asking Tarun, spending past the cap needs him, and the production key stays in Vercel only (spec 8) |
| 2026-10-04 | Plan 2 integrates on branch `plan2` (worktree `VART-wt-plan2`), so `main` stays production: the lead merges lanes into it locally; pushing and the release (PR to `main`, fast-forward after green CI, deploy) need Tarun's OK (spec 11.3-11.5) |
| 2026-10-05 | Tarun: the conflict gate counts planted conflict traps, as spec 8 says (5 in the dev pack), not keyed items; a trap is caught when at least one of its items is labelled conflict, and the date rule is gated per planted date trap the same way. The per-item numbers stay in the report, ungated (spec 8) |
| 2026-10-05 | Tarun: no faster mode; every Plan 2 task keeps the full process (implementer, review, fix rounds) |
| 2026-10-05 | Tarun: design direction C (console) for the UI; it is locked on branch `design` and waits for Plan 3 |
| 2026-10-05 | Tarun accepted the Plan 2 baseline (15/15 gates). Known issues, reported and not gated: false verified No answers and false conflicts (conflict precision 0.8571), scope notes on 1 of 3 scope traps, per-item conflict recall 0.8571 and date-rule items 0.75 |
| 2026-10-05 | Models per step from the bench, approved by Tarun: stance deepseek/deepseek-v4-pro, draft z-ai/glm-5.3-flash (reasoning at its lowest effort), judge qwen/qwen3.7-plus; classify stays deepseek/deepseek-v4-flash and recheck uses the stance model (spec 6.14) |
| 2026-10-05 | Retrieval is full-text only: recall@8 0.9738; vectors are tried only below 0.95 and kept only if they add 0.05 (not tried) (spec 6.5) |
| 2026-10-05 | Gates set from the baseline (`evals/score.py`): label accuracy 0.90, recall@8 0.95, judge faithfulness 0.95; every other gate stays at its spec value. CI replays the dev pack, fails on a missed gate or on drift in `evals/results`, and holds decide at 100% branch coverage |
| 2026-10-05 | Sample packs are not redacted; uploads and visitor answers are; citations quote the stored line (Plan 1A Ruling 10) - SECURITY.md (Plan 4) must say so |
| 2026-10-05 | `ops/setup.sh migrate` brings production to alembic head before `main` moves, because Vercel's Git integration deploys `main` at once (spec 10) |
| 2026-10-05 | Tarun: a Jev (TypeSafe) spike runs after the Plan 2 baseline: a throwaway sentence-selection stance measured against the current one, with no contract change and no merge; its output is a recommendation |
| 2026-10-05 | Tarun approved the CSF 2.0 gap check design and Plan 6A (backend and evals), on branch `spec-csf-gap` |
| 2026-10-06 | The HTTP contract is frozen after Plan 3's adversary checkpoint 1; later changes add optional fields, paths or statuses only, each with a change-log line in `docs/CONTRACTS.md` |
| 2026-10-06 | Plan 3 runs three lanes in parallel, each in its own worktree: inputs (documents, questionnaires, mapper), runs (step runner, answers, audit, export) and the UI; the lead merges them into `plan3` |
| 2026-10-06 | The sample data (`data/dev/docs`, `data/questionnaires`) ships in the function bundle from Plan 3; spec 10 had said Plan 4 |
| 2026-10-06 | csv questionnaire originals are stored too, so export can match the input |
| 2026-10-06 | A document a run used cannot be deleted, and neither can a questionnaire a run used (409) |
| 2026-10-06 | E2E answers model calls from `web/e2e/recorded.jsonl` (`LLM_MODE=replay`); the sample, export and interview flows share one sample run, so the specs stay under the 400/h per-network model-call cap |

| 2026-10-06 | Tarun chose option A for the CSF gap check: every Checked outcome is cut into NIST parts by a fixed rule, each part is a question run through the unchanged pipeline, and code combines the parts' labels (CSF spec 5.2-5.3, amended) |
| 2026-10-06 | The gap-dev key is judged blind: a judge sees NIST's text, the dev documents and the fact sheet, never engine output, and the key is derived in code from that, never hand-edited or run through the engine's combination (CSF spec 8) |
| 2026-10-06 | Tarun accepted and reported the per-part baseline: label accuracy 0.7097 (22 of 31) against the spec's 0.80, after two judged key rounds and one per-part tuning round |
| 2026-10-06 | The 6A `app/redact.py` change (a word of a found name also names that person) ships to every upload and Ask-me answer when 6A merges, before 6B: it is a privacy gain, at the cost of over-redacting a capitalised name word used as an ordinary word in the same line |
| 2026-10-06 | Tarun (6B): the gap sheet goes in both exports, the gap-report workbook and the filled questionnaire's xlsx |
| 2026-10-06 | Tarun (6B): the planted improvement plan joins the sample pack, which reverses the 6A decision that kept it gap-only; the dev keys were re-derived and the dev gates held (15/15, label accuracy 0.9326) |
| 2026-10-06 | Tarun (6B): an Ask-me answer's fills widen to the open parts of Checked outcomes in the same CSF function, not only the same topic; a fill stays a suggestion until accepted |
| 2026-10-06 | Tarun (6B): check again re-runs every part of each affected outcome, started by `r`, never by an upload; a part the visitor filled stays |
| 2026-10-06 | 6B Ruling 6: accepted per-part fills make an outcome Confirmed by you only when its label would otherwise be Covered; one filled part with Gaps stays Partly covered, and accepting one fill never locks the others |
| 2026-10-06 | 6B Ruling 13: gap-check outcomes are reviewed through Check again, not approved: bulk approve skips them, and approving or editing a gap answer answers 409 |
| 2026-10-06 | `label_accuracy` in gap-dev is reported, not gating, with its 0.80 target kept in the table and marked "reported: below target, accepted 2026-10-06", until a later plan improves stance; every other gate gates |


## Plan 4 carry-over (deferred from Plan 3)
- No 409 when a second run starts while one is running (Ruling 8): two concurrent runs double the spend. Plan 4 reconsiders it with a timeout for abandoned runs.
- A step that takes longer than 5 minutes is not handled (N1).
- An edited answer the visitor already confirmed keeps its old statement (M6).
- Text hidden inside a docx or pdf is invisible to the reader but can still be cited.
- Hidden spreadsheet rows are imported like any other row.
- Answering an interview question can deadlock against a workspace reset happening at the same moment.
- Workspace N2 (Enter on a select) needs one check in Firefox.
- The sample run is not precomputed yet; the cheapest way is to replay the dev recordings for `source = sample` runs. Tarun asked for it on 2026-10-06 ("Try with a sample company" instant, spending nothing); the draft design is in commit `1db3f3e` (Tasks 2b and 7b, reverted).
- Tarun, 2026-10-06: a step answers its claimed items concurrently, about 3-4x faster. Draft design in commit `1db3f3e` (Task 2b).
- SECURITY.md is still to write; it must carry the four known redaction gaps ("Last, First" order, accented all-caps names, single first names, lower-case names).
- A run stuck in `running` blocks document deletes until the visitor resets the workspace.

## 6A baseline (gap-dev, 2026-10-06)
Per-part design, replayed from the recording with no key. Gates: 9/9 gating pass; `label_accuracy` 0.7097 is reported
below its 0.80 target.

| Reported | Value |
|---|---|
| cost per core run | $0.0378 |
| seconds per core run | 790 |
| retrieval_recall_at_8 | 0.75 |
| part_agreement | 0.78 |

The 9 label misses of 31 Checked outcomes, each with its cause (from `gap-parts-1-diagnosis`):
- DE.CM-09, expected Covered, got Partly: stance; the data part reads lmp:13's "critical" as a stated limit.
- GV.PO-01, Covered, got Partly: retrieval; the "established" and "enforced" parts miss the key lines (NIST's own words
  rarely appear in company documents).
- ID.RA-08, Covered, got Partly: retrieval; the key's prioritized and tracked line is not reached by the "receiving"
  part.
- PR.DS-01, Covered, got Partly: retrieval; the integrity part never reaches "improper alteration or loss".
- PR.IR-03, Partly, got Covered: stance; the pair "normal and adverse situations" stays in one part, and RTO/RPO lines
  read as yes.
- PR.PS-01, Covered, got Gap: retrieval; the CI/CD line (sdp:17) is in neither part's top 8 after the NIST-literal cut.
- RC.RP-01, Covered, got Gap: stance; "once initiated from the incident response process" is a qualifier no single
  passage states.
- RS.CO-02, Partly, got Documents disagree: stance; a draft line is judged "no" against a final "yes".
- RS.MA-01, Partly, got Gap: stance; the plan line lacks the "third parties" qualifier, and one part carries both
  qualifiers.

Four misses are retrieval and five are stance; combine and the key caused none.

## 6B carry-over
From Ruling 18 (per-part design); (a) to (d) were delivered in 6B:
- (a) Per-part results persisted: done, 6B Task 2.
- (b) The runner claims csf items until their parts sum to at most 8 per step: done, 6B Task 2.
- (c) A per-part re-check, an accepted suggestion replaces that part before `combine`: done, 6B Task 4.
- (d) The inspector shows each part's status: done, 6B Tasks 3 and 6.

Carried to a later plan:
- Stance improvement: raise `label_accuracy` to its 0.80 target (qualifier and stated-limit reads; part retrieval
  vocabulary), then make it gating again.
- `app.csf.evidence` drops statements after the top-8 cut, so filter before the cut when retrieval is next touched.
  It still holds, and `reopen_changed` inherits it: a new Ask-me statement that reaches a part's top 8 changes that
  part's passages and re-opens its outcome once.

## How to run
See `CLAUDE.md` (commands) and `README.md`.
