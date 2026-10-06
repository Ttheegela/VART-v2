# VART - Plan 6B: CSF 2.0 gap check, the visitor-facing half Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A visitor runs NIST's CSF 2.0 gap check over their own documents from a Gap check view. They can:
- start a run per scope, and check it again after an upload;
- answer the Ask-me outcomes;
- inspect each outcome part by part, next to NIST's text and the cited lines;
- export a gap-report sheet, alone or inside their filled questionnaire.

The sample pack gains the planted improvement plan, so the live demo shows a stated non-compliance. "Try with a sample company" is instant and spends no model call: it copies a run the real engine made once. A live run answers a step's items at the same time, so 64 items take about 3 minutes instead of 11. Every label is decided by code.

**Architecture:** Part 0 (Task 1) adds one additive migration (`run_items.parts`, `suggestions.part`) and freezes the contract additions:
- two paths under `/api/gap/{scope}` (answering 501 until built);
- the optional fields `AnswerDetail.parts` and `SuggestionOut.part`;
- the gap sheet in both exports;
- the new `app/csf.py` signatures in `docs/CONTRACTS.md`.

After adversary checkpoint 1, three lanes run in parallel on disjoint files:
- **api** (Tasks 2, 2b, 3, 4):
  - the step runner answers csf items part by part, claiming outcomes until their parts reach 8 and storing each part's result as it lands;
  - a step answers its claimed items, or parts, at the same time, each worker on its own session (Task 2b, speed-up A);
  - the gap endpoints, the inspector's parts, and the gap-report sheet (alone, and inside a questionnaire's xlsx);
  - check again (every part of each affected outcome), Ask-me answers that fill Checked parts in the same CSF function, and re-decide per part.
- **ui** (Tasks 5-6): the Gap check view (tab 6) and its inspector, built against the generated types and the fetch mock.
- **data** (Task 7, the lead): the planted `security-improvement-plan.md` moves from the gap-only extension into the dev pack, which is also the sample pack. The dev keys are re-derived from the fact sheet and the dev eval is re-recorded. If a gating dev gate fails, the plan stops at Tarun.

The lead merges the three lanes into `plan6b` (Task 7b Step 1).
- Task 7b (speed-up B) makes "Try with a sample company" copy a precomputed run of the sample questionnaire and of the core gap check. The lead generates the snapshot once, with the eval key.
- Task 8 re-records the E2E suite with one new Playwright flow.
- The whole-branch adversary checkpoint, the docs, the final review and the release plan follow (Task 9).

Decide, stance, the draft prompt and `answer_retrieved` do not change. Retrieval gains one optional keyword, with its default unchanged (Task 4, adversary-1 I4). Model calls are made in three places:
- Task 7's new document re-records the dev eval;
- Task 7b generates the snapshot;
- Task 8 re-records the E2E.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic (JSONB), openpyxl, pytest with Postgres, the datakit fact-sheet tools; React 19 + Vite + TypeScript + Tailwind v4, Vitest + Testing Library, Playwright with `LLM_MODE=replay`.

**Spec:** `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md`:
- section 5: 5.1 start, 5.4 Ask me, 5.5 not checked, 5.6 per-part re-check, 5.7 cost and claim rule;
- section 7: view, export, copy;
- section 8: the planted cases and the E2E;
- section 11: definition of done.

It sits on the main spec `docs/superpowers/specs/2026-10-03-vart-v2-design.md`: 6.3 step runner, 6.7 re-decide, 6.9 interview, 6.10 export, 6.12 API, 8 dev-pack gates.

Other inputs:
- the 6A plan `docs/superpowers/plans/2026-10-05-vart-csf-plan6a-backend.md` (Task 8 and its 6B carries);
- `docs/PROGRESS.md` ("6B carry-over" (a)-(d));
- the lead's 6A ledger, Rulings 14-21;
- `design.md` (direction C, binding for UI);
- `docs/CONTRACTS.md` (the frozen HTTP contract: changes may only add optional fields, paths or statuses, each with a change-log line).

## Execution notes (read first)

- **Branches and worktrees.** Integration branch `plan6b` in `~/Desktop/portfolio/projects/VART-wt-plan6b`, from released `main` at `d071aa2` (Plans 3 and 6A live; Neon at `a7c3e9d1b2f4`). Part 0 (Task 1) runs there. After adversary checkpoint 1, the lead creates three lane worktrees from `plan6b`:

  | Lane | Branch | Worktree | Tasks | Database |
  |---|---|---|---|---|
  | api | `plan6b-api` | `~/Desktop/portfolio/projects/VART-wt-6b-api` | 2, 2b, 3, 4, in order | `vart_test_6b_api` |
  | ui | `plan6b-ui` | `~/Desktop/portfolio/projects/VART-wt-6b-ui` | 5-6, in order | none |
  | data | `plan6b-data` | `~/Desktop/portfolio/projects/VART-wt-6b-data` | 7, the lead | `vart_test_6b_data` |

  The lead merges all three into `plan6b` (Task 7b Step 1); Task 7b then runs on `plan6b`, because it touches files from both the api and the ui lane. Part 0, integration and the E2E use `vart_test_plan6b`. The lead creates each database once from the main checkout: `docker compose exec db createdb -U vart <name>`.
- **Decisions.** Tarun answered open questions 1-4 on 2026-10-06; decisions 3, 5, 7 and 8 are his answers.
  1. **One migration, additive** (`c4e8a2d6f1b3`). Carry (a) needs somewhere to keep a part's result before its outcome is whole, and carry (c) needs a fill to name its part. Two columns do it, and no table:
     - `run_items.parts JSONB NOT NULL DEFAULT '{}'`, keyed `"1"`..`"n"`, each the part's stored result plus its wording;
     - `suggestions.part SMALLINT NOT NULL DEFAULT 0` (0 is a whole item), with `uq_suggestions_fill` widened by `part`.

     Old code runs on the new schema unchanged, so Tarun migrates Neon before `main` moves, as for every release.
  2. **Where the parts live.** A part's stored result is `{"question": <part wording>, **runs._raw(result)}`, plus `"statement_id"` when an accepted fill wrote it. The `answers` row stays the outcome's display record (CSF spec 5.3). Its `chunk_ids` are the union of the parts' chunk ids, so `redecide` still finds it, and it has no stances of its own.
  3. **Check again re-runs every part of each affected outcome** (CSF spec 5.6, as written). Adversary checkpoint 1 tightened what "affected" means (Ruling 4):
     - passages are compared as sets;
     - a Checked part's retrieval leaves statements out before its top 8 (`retrieve(..., exclude_kinds=("statement",))`, lead's OK under rule 10), so an Ask-me answer alone re-opens nothing;
     - a part judged by another stance prompt or model counts as changed (M5);
     - open per-part fills survive a re-open (I4). The trigger is `r` on a scope whose run is done (`POST /api/gap/{scope}/run`); an upload never starts model calls by itself, and the view offers "Check again". An outcome counts as affected when any of its parts now retrieves other passages than it was judged on, when its wording changed, or when it is incomplete. The comparison is retrieval only, with no model call. Every machine-judged part of an affected outcome is dropped and runs again. A part filled by a fill the visitor accepted stays: it is the visitor's work, like an approved outcome.
  4. **Paths.** `GET /api/gap/{scope}` and `POST /api/gap/{scope}/run`. `Mapping.scope`, kept free in Plan 3 for 6B, stays unused, because `GapOut.scope` and the questionnaire's stored mapping carry the scope.
  5. **The gap sheet goes in both exports.**
     - A gap-check run's export (`GET /api/runs/{id}/export`) is the gap-report workbook. That path answered 409 for such a run before, so the change adds a status there.
     - A questionnaire run's xlsx export also carries the workspace's latest *done* gap-check run as a `Gap report` sheet. If the visitor's workbook already has a sheet of that name, the new sheet is `Gap report (2)`, and so on. Row 1 states the scope and the run date. When no gap-check run is done, the export is unchanged.
     - A csv export cannot hold a second sheet and is unchanged.
     - Every cell is inert, as before.
  6. **800-53 controls** link to one NIST page (`csf.CONTROLS_URL`), not one page per control. As with 6A's decision 3, no per-control URL could be verified (the Reference Tool's deep links are single-page-app routes). The lead checks the URL in a browser in Task 1 Step 7.
  7. **The sample pack gains `security-improvement-plan.md`** (Task 7), so the live demo shows Not met (stated) on ID.RA-02 and DE.AE-07. The sample pack is `data/dev/docs`, so the dev eval sees the new document too.
     - The document, its statements, the controls only it names, and its traps move from `data/dev/gap/facts.yaml` into `data/dev/facts.yaml`.
     - The questionnaire keys are re-derived (`python -m datakit.derive_key dev`), never edited by hand.
     - The dev eval is re-recorded with the eval key, and its gates are re-checked. If a gating gate fails, including `label_accuracy` 0.90 (82 of 89 today; at least 81 of 89 passes), the plan stops and the lead takes it to Tarun. No gate is lowered and nothing is tuned.
     - `gap-dev` already loads the document, so its results must stay byte-identical.
  8. **Fills widen to the same CSF function.** In a gap-check run, an Ask-me answer is re-checked against the open parts of Checked outcomes in the answered outcome's CSF function (all five Ask-me outcomes are Govern, so they reach GV.PO-01 and GV.PO-02's parts). A questionnaire keeps spec 6.9's same-topic rule.
     - `app.interview.recheck` is frozen and filters by topic, so `app/questions.py` calls it once per topic group; nothing frozen changes.
     - The calls stay under the per-answer cap: at most `MAX_RECHECKS` (8) re-checks within `RECHECK_SECONDS` (90 s), each spent through the per-network `llm` counter.
     - A fill stays a suggestion until the visitor accepts it.
     - An accepted fill is the visitor's word, never a document's (adversary-1 I3, Ruling 4). The explanation names it under "Confirmed by you: part n", and the gap sheet marks its quote "(your answer)". The outcome reads Confirmed by you once every part that is not a Gap was filled; a stated No or a disagreement on an unfilled part still decides the label.
  9. **Questions for you on a gap-check run holds its Ask-me outcomes only** (6A decision 6, now enforced in `ensure_questions`). As for any run, they are planned once the run is done.
  10. **The view's path is `workspace / csf 2.0 / <scope>`.** The API has no company name for spec 7's `<company>`.
  11. **The gap view's filter toggles have no single keys.** `g i p d s o a r e` are taken, and spare letters would read as noise. The toggles are Tab-reached buttons, like the Workspace row actions; design.md gets a line.
  12. **A step answers its claimed items at the same time** (Tarun, 2026-10-06; Task 2b). Up to `STEP_ITEMS` questionnaire items, or up to `STEP_PARTS` gap-check parts, run in a thread pool:
      - each worker has its own session, spender and cost meter;
      - the request's thread writes the answers in claim order and raises after writing.

      Calls per run are unchanged; only the wall-clock drops (about 3 min for 64 items, about 4 min for a core gap run).
  13. **The precomputed sample run** (Tarun, 2026-10-06; Task 7b). It moves from the Plan 4 carry-over into 6B.
      - Coverage: the sample questionnaire and the core gap check over the untouched sample pack.
      - The snapshot `data/dev/sample-run.json` is generated by `scripts/sample_snapshot.py` (the lead, eval key) and never hand-written.
      - Its digest covers the sample documents, the questionnaire, the prompt versions, the step models and the core CSF data.
      - A stale snapshot is never used: the run goes live, and a test fails in CI.
      - Re-run live (`?live=true`) always calls the engine. A function scope always runs live.
- **Network budget for the E2E.** The CI suite shares one per-network cap of 400 model calls an hour.
  - After Task 7b, the sample flow's run and the gap flow's core check are copied, with no model call.
  - What still calls a model:
    - the upload flow, 20 items, about 40 calls;
    - the sample interview's re-check, up to 8;
    - the Govern re-checks after the Ask-me answer, up to 7;
    - one live Recover part.
  - Total about 55, down from about 231. Task 8 Step 4 measures it from `ip_limits` after a full replay.
  - Task 2b makes the calls arrive faster, but the cap counts calls per hour, so the total is what matters.
- **Eval-key spend** (lead only; `~/.config/vart/eval.env`, $5 cap):

  | Task | Spend |
  |---|---|
  | 1-6, 2b | none |
  | 7 | dev re-record under $0.25 (the new document may re-rank most items, adversary-1 M10); gap-dev $0.04 only if it drifts |
  | 7b | the sample snapshot about $0.08: 64 questionnaire items about $0.04, a core gap run about $0.04 |
  | 8 | E2E re-record about $0.03: the upload flow, the re-checks, one Recover part |
  | Total | about $0.20-0.40; ask Tarun if the key's remaining credit is under $1 |

## Lanes

| Part | Tasks | Runs on | Implementer | Reviewer |
|---|---|---|---|---|
| Part 0: migration and contract additions | 1 | `plan6b` | lead (Opus 5.5) | Opus |
| Lane api | 2, 2b, 3, 4 | `plan6b-api` | Opus 5.5 (2, 2b, 4), Sonnet 5.5 (3) | Opus (2, 2b, 4), Sonnet (3) |
| Lane ui | 5, 6 | `plan6b-ui` | Opus 5.5 | Opus |
| Lane data | 7 | `plan6b-data` | lead (Opus 5.5; recording) | Opus (keys derived, gates held) |
| Merge and precomputed sample | 7b | `plan6b` | lead merges; Opus 5.5 implements; lead generates the snapshot | Opus |
| E2E | 8 | `plan6b` | lead | Opus |
| Checkpoint, docs, release | 9 | `plan6b` | lead | final Opus review; Tarun approves every outward step |

The lanes share only Task 1's frozen output (`openapi.json`, `web/src/lib/api-types.ts`, the migration), so their files are disjoint. The data lane touches only `data/dev`, the sample list, two count tests, and the dev eval's recordings and results. Inside the api lane, the tasks run in order:
- Task 2b rewrites Task 2's step loop;
- Task 3 calls the runner;
- Task 4 changes Task 3's POST handler.

Task 7b needs all three lanes merged (Task 7's 23-document pack; the api lane's endpoints; the ui lane's run grid), so it runs after them on `plan6b`. Task 8 records after Task 7b, because the copied runs change what the E2E calls. Inside the ui lane, Task 6 renders its drawer inside Task 5's view.

## Global Constraints

- Every commit message ends with exactly this paragraph: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (also when a Sonnet model commits).
- Never open, list, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/`; never type the sponsor's company or people names.
- Never use `git stash`. Set work aside with a WIP commit on your own branch.
- Tests never touch the network or a real key (pytest-socket): model calls go through `tests/fakes.py` (`FakeLLM`, `ByStepLLM`). Only the lead calls a real model, with the eval key:
  - the dev eval in Task 7;
  - the sample snapshot in Task 7b;
  - the E2E (replayed from `web/e2e/recorded.jsonl`) in Task 8.

  `data/dev/sample-run.json` is written only by `scripts/sample_snapshot.py`.
- Concurrency (Task 2b): a `Session` never crosses threads. Every worker spends before its call and holds no transaction across it, and a worker's error comes back to the request's thread with its cost.
- Backend chain, green before every commit (run `ruff format .` first; with `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/<lane db> && export DATABASE_URL=$TEST_DATABASE_URL`): `ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check`. Never run `docker compose` from a worktree.
- Frontend chain: `cd web && npm run lint && npm test && npm run build`, then `python scripts/check_monochrome.py` from the repo root.
- After any change to `app/api/schemas.py` or a route: `python scripts/export_openapi.py && (cd web && npm run gen:api)`, and commit both files. No hand-written request or response type under `web/src`.
- Hard rule 11: engine code spends the budget before every model call and holds no database transaction across one. Each part reaches a model only through `app.csf.check_part` → `answer_retrieved`; a re-check only through `app.interview.recheck`. Ask-me and not-checked outcomes make no model call of their own (CSF spec 5.4-5.5).
- `ck_answers_cited` is unchanged: no Covered or Partly covered result without a citation (CSF spec 6).
- Frozen, never edited by a task: `app/text.py`, `app/patterns.py`, `app/contracts.py`, `app/decide.py`, `app/stance.py`, `app/draft.py`, `app/pipeline.py`, `app/retrieve.py` (except Task 4's `exclude_kinds` keyword, approved under rule 10 by Ruling 4), `app/interview.py`, `app/ingest/`, `app/redact.py`, every prompt, `data/csf/`, `evals/*.py`, and the gates in `evals/score.py`.
  - `data/dev` and the dev eval's recordings and results change only in Task 7, and only as it says.
  - After adversary checkpoint 1, the Task 1 additions to `app/api/schemas.py`, and every path, method and status in `openapi.json`, are frozen too. A change needs the lead's OK and a change-log line in `docs/CONTRACTS.md`.
- Keys come only from the fact sheet: `data/dev/key/*.yaml` are written by `python -m datakit.derive_key dev` and `python -m datakit.gap dev`, never by hand.
- No gate is lowered. When a gating gate fails after Task 7's re-record, the plan stops and the lead takes the misses to Tarun.
- The evals do not move outside Task 7: `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results` passes after every api-lane task (against the lane's base) and on `plan6b` after Task 7b's merge.
- CSF spec 4: "What the visitor sees as 'the framework' is always NIST's verbatim `outcome` text." The view, the inspector and both exports show `outcome` unedited.
- CSF spec 5.5: "Not-checked outcomes make no model call and carry no label." CSF spec 2: "Every finding reads 'possible gap, review it'; the view and the export say so."
- Copy, exactly (CSF spec 7): `Possible gap — review it` and `Not legal advice. CSF 2.0 text © NIST, public domain.` (an em dash, and the © sign).
- The status line counts tiers from the rows and is never typed in. For the core it reads `checked 31 · ask me 5 · not checked 70 · of 106`.
- Monochrome UI only: black, white and `neutral-*` (`scripts/check_monochrome.py`); labels in words, never colour alone; design.md direction C components (28px rows, filter line, command line, inspector drawer, key hints).
- Production migrations run from Tarun's terminal (`ops/setup.sh migrate`), never in a build or by an agent; the migration reaches Neon before `main` moves.
- The eval key (`VART_EVAL_OPENROUTER_API_KEY` in `~/.config/vart/eval.env`) is loaded inside the command and never printed; spending past its $5 cap needs Tarun.
- Each task owns the files it lists; the reviewer rejects edits outside them. The same failure twice: stop and report. Never weaken, skip or delete a test; a count a test pins changes only when the data it counts changes (Task 7).

## Review Focus

1. **A step refused by the hourly stance cap in the middle of an outcome.** A second core run in the same hour does this (CSF spec 5.7). Expect: the parts already paid for stay stored; no answer row appears until every part is there; the next step pays only for the parts still missing; each paid call is counted once in `runs.cost_usd`. Pinned in Task 2 (`test_a_refused_budget_keeps_the_paid_parts_and_the_next_step_pays_only_the_rest`).
2. **A metadata override after a gap run** (a document marked draft or not evidence). Expect: each part is decided again from its own stored stances, then the parts are combined again. Decide must never run over the outcome row's empty stances, which would turn every outcome into Gap. A part filled by an accepted fill keeps its result. Pinned in Task 4 (`test_a_metadata_override_redecides_each_part_and_recombines`).
3. **`r` pressed again on a done scope**, with or without a new upload, or pressed in two tabs at once. Expect:
   - every machine-judged part of each affected outcome runs again, and unaffected outcomes keep their results;
   - the visitor's edited, approved, confirmed or not-applicable outcomes and accepted parts stay;
   - with nothing changed, the run stays done and no model is called;
   - two presses re-open an outcome once.

   - an Ask-me answer alone re-opens nothing; the same passages in another order are the same evidence; open per-part fills survive (adversary-1 I4);
   - two first presses make one run (adversary-1 I2).

   Pinned in Task 4: `test_check_again_reruns_every_part_of_an_affected_outcome`, `test_check_again_keeps_the_visitors_outcomes_and_accepted_parts`, `test_check_again_with_nothing_changed_stays_done`, `test_check_again_after_an_upload_reopens_the_outcomes_the_new_document_reaches`, `test_an_ask_me_answer_alone_reopens_nothing`, `test_the_same_passages_in_another_order_are_the_same_evidence`. Pinned in Task 3: `test_two_first_presses_at_once_make_one_run`.
4. **A deploy rewords a part** while results for the old wording are stored, mid-run or after. Expect: a stored part whose wording differs from the deployed one runs again; the others are kept. Pinned in Task 2 (`test_a_stored_part_with_other_wording_is_run_again`).
5. **Coverage overstated in the view or an export.** That would be:
   - a label on a not-checked outcome;
   - an unanswered Ask-me outcome shown as anything but Not answered;
   - counts typed in;
   - an export that leaves out unchecked outcomes;
   - a gap sheet slipped into a questionnaire export without its scope and date.

   Expect: labels come only from `csf.gap_label`; the status line is counted from the rows; both exports list every outcome in scope, the unchecked ones as "Not checked in this version", under a row that names the scope and run date. Pinned in Task 3 (`test_the_view_lists_every_outcome_and_labels_only_what_was_checked`, `test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells`, `test_a_questionnaire_export_carries_the_latest_gap_sheet_only_when_one_exists`) and Task 5 (`it("counts the coverage line from the rows")`).
6. **A loosely related Ask-me answer counted as evidence.** For example, a Govern answer about risk appetite read as proof that the policy is "enforced". Expect:
   - it fills nothing by itself: a fill is a suggestion until the visitor accepts it;
   - each fill quotes a line of the visitor's own stored, redacted statement (decide's containment check);
   - it reaches only Checked parts in the same CSF function, never another function's;
   - it makes at most 8 re-check calls within 90 s per answer.

   - an accepted fill never makes an outcome read Covered: it reads Confirmed by you, and its quote is marked "(your answer)" (adversary-1 I3).

   Pinned in Task 4 (`test_a_govern_answer_suggests_fills_for_govern_parts_only_until_accepted`, `test_an_answer_never_fills_another_functions_parts`, `test_a_filled_part_never_makes_documents_read_covered`) and Task 3 (the "(your answer)" cell in `test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells`).
7. **Several workers hitting one condition at once** (Task 2b). Conditions: a budget refusal, a provider outage or the deadline in the middle of a concurrent step, or two parts of one outcome finishing together. Expect:
   - every paid call is counted once, and every answer that came back is written once;
   - refused and untried items go back with their attempt refunded, and outage-hit items keep theirs;
   - nothing is written as failed for an outage, and the 503 comes only when nothing was answered;
   - no stored part is lost to a concurrent write, and the answers come back in questionnaire order;
   - no worker holds a transaction across its call, and the spend counters stay exact.

   Pinned in Task 2b: `test_four_items_take_about_a_quarter_of_the_sequential_time`, `test_a_gap_outcomes_parts_run_at_once`, `test_spending_is_exact_under_concurrency`, `test_a_budget_refusal_mid_step_writes_what_was_paid_and_gives_the_rest_back`, `test_an_outage_mid_step_writes_the_others_and_keeps_the_attempt_of_the_item_that_met_it`, `test_an_outage_on_every_item_is_a_503_with_no_failed_answer`, `test_no_worker_holds_a_transaction_while_it_calls_a_model`.
8. **A stale or mismatched sample snapshot.** This happens after a prompt, model, sample-document, questionnaire or CSF-data change, or in a workspace that is no longer the plain sample (an upload, an override, an answered question). Expect:
   - the snapshot is never copied, and the run goes live;
   - CI fails until the lead regenerates the snapshot;
   - a copied run keeps every invariant: citations re-read from the visitor's own documents, `ck_answers_cited`, done at $0, marked precomputed;
   - Re-run live, Questions for you, the re-check and re-decide work on it.

   Pinned in Task 7b: `test_the_sample_snapshot_is_current`, `test_the_digest_moves_with_every_input`, `test_a_stale_snapshot_is_never_copied`, `test_an_override_or_an_upload_falls_back_to_a_live_run`, `test_try_with_a_sample_company_copies_the_snapshot_with_no_model_call`, `test_questions_rechecks_and_redecide_work_on_a_copied_run`, `test_re_run_live_runs_the_engine`, `test_the_core_gap_check_is_copied_too`.

## Review gates (run by the lead)

- **Adversary checkpoint 1** (Fable 5.1) after Task 1, before the lane worktrees exist. It reads the migration, the schema additions, the stubs, `openapi.json`, the CONTRACTS.md lines and this plan's Tasks 2-7, and asks:
  - what does the view or the inspector need that no field carries;
  - what can a visitor trigger that has no error shape;
  - can a stored part outlive the documents or the wording it describes;
  - does any path let an Ask-me answer or a not-checked outcome reach a model, other than the re-check of a stored answer;
  - can moving the planted document change a key by hand rather than by derivation?

  Fixes land in Part 0, with the types regenerated, before the lanes start. **Recheck** (Ruling 3): after Rulings 3-4 are folded in and the Task 1 fix round lands, the same adversary rechecks the amended plan before the lanes start. The recheck covers:
  - Task 2b's concurrency (threads and sessions, the refusal, outage and deadline semantics, the edited tests);
  - Task 7b's snapshot (staleness, id mapping, the fallback to a live run, the contract additions);
  - Task 4's `retrieve` keyword.
- **Two-failure rule**: the same failure twice in a task stops it for a Fable look.
- **Task 7's gate check** is a stop point: a gating dev gate below its value goes to Tarun before anything else merges.
- **Adversary checkpoint 2** (Fable 5.1) on `main..plan6b` after Task 8 (Task 9 Step 1): what input, label, lock order, copy, fill, thread or stale snapshot did everyone miss? Fixes land before the docs and the final review.
- **Final Opus review** of `main..plan6b` after Task 9 Step 6. Pushing, the pull request, the migration and the fast-forward of `main` are Tarun's.

## File Structure

```
migrations/versions/c4e8a2d6f1b3_csf_parts.py   NEW (T1)  run_items.parts, suggestions.part, widened uq_suggestions_fill
app/db/models.py                                MOD (T1)  RunItem.parts, SuggestedFill.part
app/api/schemas.py                              MOD (T1)  GapRow, GapOut, PartOut; AnswerDetail.parts; SuggestionOut.part
app/api/gap.py                                  NEW (T1 stubs, T3 built, T4 check again)
app/main.py                                     MOD (T1)  include the gap router
openapi.json, web/src/lib/api-types.ts          GEN (T1, T3)  regenerated
docs/CONTRACTS.md                               MOD (T1, T9)
tests/test_models.py, tests/test_openapi.py     MOD (T1)
app/csf.py                                      MOD (T2 current_mapping, check_part, part_result; T3 CONTROLS_URL)
app/runs.py                                     MOD (T2 per-part runner, outcome_values, _is_current; T2b worker pool; T4 reopen_changed, Confirmed by you)
tests/test_runs_concurrent.py                   NEW (T2b)
tests/test_runs.py                              MOD (T2b)  one outage test's expected numbers
app/retrieve.py, tests/test_retrieve.py         MOD (T4)  exclude_kinds keyword (rule 10, Ruling 4)
tests/test_csf_parts.py                         MOD (T2)
tests/test_runs_csf.py                          NEW (T2, T4)
app/api/answers.py                              MOD (T3)  AnswerDetail.parts
app/export.py, app/api/export.py                MOD (T3)  GapSheet; gap-report workbook; gap sheet in a questionnaire's xlsx
tests/test_api_gap.py                           NEW (T3, T4)
tests/test_api_errors.py                        MOD (T3)  gap paths from STUBS to COVERED (Ruling 2)
tests/test_export.py                            MOD (T3)
app/questions.py, app/api/questions.py          MOD (T4)  Ask-me only; per-part fills in the same CSF function; accept per part
app/redecide.py, tests/test_redecide.py         MOD (T4)  re-decide per part
tests/test_questions_csf.py                     NEW (T4)
web/src/lib/{api,route,labels}.ts               MOD (T5)
web/src/components/{ui,Shell}.tsx               MOD (T5)  GapChip; tab 6; key sheet lines
web/src/App.tsx, web/src/views/Export.tsx       MOD (T5)  route; the export view names the gap sheet
web/src/views/GapCheck.tsx (+ .test.tsx)        NEW (T5), MOD (T6)
web/src/test/mockApi.ts                         MOD (T5, T6)
design.md                                       MOD (T5)
web/src/views/EvidenceDrawer.tsx                MOD (T6)  DrawerFrame and DroppedList extracted, behaviour unchanged
web/src/views/Questions.tsx                     MOD (T6)  QuestionCard exported
web/src/views/GapDrawer.tsx (+ .test.tsx)       NEW (T6)
data/dev/src/sip.md                             NEW (T7)  the planted plan's source
data/dev/docs/security-improvement-plan.md      NEW (T7)  rendered; replaces data/dev/gap/docs/security-improvement-plan.md (deleted)
data/dev/facts.yaml, data/dev/gap/facts.yaml    MOD (T7)  the document's entries move from the gap extension to the dev sheet
data/dev/key/vsq-a.yaml, data/dev/key/mvsp-b.yaml   MOD (T7, re-derived)  data/dev/key/csf-core.yaml re-derived, unchanged
app/api/documents.py                            MOD (T7)  SAMPLE_ORDER gains the document (23)
tests/test_api_documents.py, tests/test_eval_run.py   MOD (T7)  22 -> 23 sample documents
evals/recorded/dev.jsonl, evals/results/latest.{json,md}   MOD (T7, the lead's record run)
app/sample_run.py, scripts/sample_snapshot.py   NEW (T7b)
data/dev/sample-run.json                        NEW (T7b, written by the script)
tests/test_sample_run.py                        NEW (T7b)
app/api/runs.py, .vercelignore                  MOD (T7b)  live query parameter, RunOut.precomputed; ship the snapshot
web/src/views/RunGrid.tsx (+ .test.tsx)         MOD (T7b)  Re-run live asks for live; precomputed shown
web/e2e/gap.spec.ts                             NEW (T8)
web/e2e/recorded.jsonl                          MOD (T8, the lead's record run)
README.md, CLAUDE.md, docs/PROGRESS.md, the CSF spec   MOD (T9)
```

---

### Task 1: Migration and contract additions (Part 0)

**Runs on:** `plan6b`, by the lead. **Reviewer:** Opus. **Eval key:** none. **Then:** adversary checkpoint 1.

**Files:**
- Create: `migrations/versions/c4e8a2d6f1b3_csf_parts.py`, `app/api/gap.py`
- Modify: `app/db/models.py` (`RunItem`, `SuggestedFill`), `app/api/schemas.py`, `app/main.py:58-60`, `tests/test_models.py`, `tests/test_openapi.py:19-47`, `docs/CONTRACTS.md`
- Regenerate: `openapi.json`, `web/src/lib/api-types.ts`

**Interfaces:**
- Consumes: `app.csf.GapLabel`, `app.csf.PartLabel`, `app.csf.Scope`, `app.csf.Tier` (6A, unchanged).
- Produces:
  - `RunItem.parts: Mapped[dict[str, Any]]`, default `{}`; `SuggestedFill.part: Mapped[int]`, default `0`; `uq_suggestions_fill` on `(run_id, item_id, statement_id, part)`.
  - In `app/api/schemas.py`: `GapScope`, `GapRow`, `GapOut`, `PartOut`; `AnswerDetail.parts: list[PartOut] = []`; `SuggestionOut.part: int = 0`.
  - Paths `GET /api/gap/{scope}` → `GapOut` and `POST /api/gap/{scope}/run` → `RunOut` (stubs answering 501 until Task 3).
  - In `web/src/lib/api-types.ts`: `components["schemas"]["GapOut" | "GapRow" | "PartOut"]`.
  - Recorded in `docs/CONTRACTS.md` for Tasks 2-4: `csf.current_mapping(scope) -> dict[str, str]`, `csf.check_part(session, workspace_id, o, n, llm, models, spend) -> ItemResult`, `csf.part_result(o, n, raw) -> ItemResult`, `csf.CONTROLS_URL: str`, `runs.STEP_PARTS = 8`, `runs.outcome_values(o, parts) -> dict[str, Any]`, `runs.reopen_changed(session, workspace_id, run_id) -> int`.

- [ ] **Step 1: Write the failing model tests**

Append to `tests/test_models.py` (it already imports `pytest`, `Session`, `IntegrityError` and `tests.factories as f`; add any of them that is missing):

```python
def test_a_fill_is_unique_per_part_of_an_item(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
        it = f.item(s, q, csf_id="GV.PO-01", code="GV.PO-01", row_ref="GV.PO-01")
        r = f.run(s, q)
        st = f.document(s, ws, source="statement", kind="statement", filename="answer-001.txt")
        f.suggestion(s, r, it, st, part=1)
        f.suggestion(s, r, it, st, part=2)  # another part of the same outcome, from the same answer
        s.commit()
        with pytest.raises(IntegrityError, match="uq_suggestions_fill"):
            f.suggestion(s, r, it, st, part=2)


def test_run_item_parts_start_empty_and_must_be_an_object(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
        it = f.item(s, q, csf_id="PR.DS-11", code="PR.DS-11", row_ref="PR.DS-11")
        r = f.run(s, q)
        ri = RunItem(run_id=r.id, item_id=it.id)
        s.add(ri)
        s.commit()
        s.refresh(ri)
        assert ri.parts == {}
        ri.parts = []  # type: ignore[assignment]
        with pytest.raises(IntegrityError, match="ck_run_items_parts"):
            s.commit()
```

Add `RunItem` to the file's `from app.db.models import ...` line if it is not there.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_models.py -k "unique_per_part or start_empty" -v`
Expected: FAIL. `SuggestedFill` has no `part`, and `RunItem` has no `parts`.

- [ ] **Step 3: Write the migration and the models**

`migrations/versions/c4e8a2d6f1b3_csf_parts.py`:

```python
"""csf parts: per-part results and per-part fills

Revision ID: c4e8a2d6f1b3
Revises: a7c3e9d1b2f4
Create Date: 2026-10-06 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4e8a2d6f1b3"
down_revision: Union[str, Sequence[str], None] = "a7c3e9d1b2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Plan 6B, additive (CSF spec 5.6-5.7): a CSF outcome's part results are stored as they land
    (run_items.parts, carry a), and a suggested fill names the part it is for (suggestions.part, 0 for a whole
    item, carry c). Existing rows get '{}' and 0. The code before 6B never reads either column, and its
    untargeted ON CONFLICT DO NOTHING works with the widened unique key."""
    op.add_column(
        "run_items",
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.create_check_constraint("ck_run_items_parts", "run_items", "jsonb_typeof(parts) = 'object'")
    op.add_column("suggestions", sa.Column("part", sa.SmallInteger(), server_default="0", nullable=False))
    op.create_check_constraint("ck_suggestions_part", "suggestions", "part >= 0")
    op.drop_constraint("uq_suggestions_fill", "suggestions", type_="unique")
    op.create_unique_constraint(
        "uq_suggestions_fill", "suggestions", ["run_id", "item_id", "statement_id", "part"]
    )


def downgrade() -> None:
    """Refuses while per-part fills exist: the narrower key could not hold two parts of one item."""
    parts = op.get_bind().exec_driver_sql("SELECT count(*) FROM suggestions WHERE part > 0").scalar()
    if parts:
        raise RuntimeError(f"{parts} suggestion(s) are for one part; delete them by hand before downgrading")
    op.drop_constraint("uq_suggestions_fill", "suggestions", type_="unique")
    op.create_unique_constraint("uq_suggestions_fill", "suggestions", ["run_id", "item_id", "statement_id"])
    op.drop_constraint("ck_suggestions_part", "suggestions", type_="check")
    op.drop_column("suggestions", "part")
    op.drop_constraint("ck_run_items_parts", "run_items", type_="check")
    op.drop_column("run_items", "parts")
```

In `app/db/models.py`, add `SmallInteger` to the `sqlalchemy` import. In `class RunItem`, after `attempts`:

```python
    # A CSF outcome's part results as they land (CSF spec 5.7): {"1": {"question": ..., **runs._raw(...)}, ...};
    # a step refused mid-outcome resumes from here without paying again. Empty for a questionnaire item.
    parts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
```

and in its `__table_args__`, after `ck_run_items_state`:

```python
        CheckConstraint("jsonb_typeof(parts) = 'object'", name="ck_run_items_parts"),
```

In `class SuggestedFill`, after `status`:

```python
    part: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")  # CSF spec 5.6; 0: the item
```

and in its `__table_args__`, replace the `uq_suggestions_fill` line and add the check:

```python
        UniqueConstraint("run_id", "item_id", "statement_id", "part", name="uq_suggestions_fill"),
        CheckConstraint("part >= 0", name="ck_suggestions_part"),
```

- [ ] **Step 4: Run the model tests and `alembic check`**

Run: `pytest tests/test_models.py -v && alembic upgrade head && alembic check`
Expected: PASS, including `test_migrated_check_constraints_match_the_models`. `alembic check` reports "No new upgrade operations detected".

- [ ] **Step 5: Write the failing contract test**

In `tests/test_openapi.py`, add two lines to `CONTRACT`, after `("/api/audit", "get"),`:

```python
    ("/api/gap/{scope}", "get"),
    ("/api/gap/{scope}/run", "post"),
```

Run: `pytest tests/test_openapi.py -v`
Expected: FAIL on `test_the_frozen_contract_is_exactly_these_operations`: the two paths do not exist.

- [ ] **Step 6: Write the schema additions, the stubs and the router line**

In `app/api/schemas.py`, add the import `from app.csf import GapLabel, PartLabel, Tier` and `from app.csf import Scope as CsfScope` (this file already has a `Scope` for document scopes). In `class SuggestionOut`, after `status`:

```python
    part: int = 0  # Plan 6B: the part of a CSF outcome this fill is for (CSF spec 5.6); 0: the whole item
```

Add a `PartOut` class above `class AnswerDetail`, and give `AnswerDetail` a last field:

```python
class PartOut(BaseModel):
    """One part of a Checked CSF outcome (CSF spec 5.2, carry d): its own label and its own cited lines, each
    with the document's status (a draft-only quote shows `draft`)."""

    n: int  # 1-based, in NIST's order
    question: str
    label: PartLabel
    citations: list[CitationOut]
    dropped: list[DroppedOut]
    from_statement: bool  # an accepted fill from the visitor's answer replaced this part (CSF spec 5.6)
```

```python
    parts: list[PartOut] = []  # Plan 6B: a Checked CSF outcome's parts, in NIST's order; [] otherwise
```

Append at the end of the file:

```python
# ------------------------------------------------------------------ gap check (Plan 6B)
GapScope = CsfScope  # "core" or one CSF function, lowercase


class GapRow(BaseModel):
    """One CSF 2.0 outcome in the Gap check view (CSF spec 7)."""

    csf_id: str
    function: str
    category: str
    outcome: str  # NIST's text, verbatim (CSF spec 4)
    related_controls: list[str]  # SP 800-53 Rev 5.2.0 identifiers
    source_url: str
    tier: Tier
    item_id: uuid.UUID | None  # None for a not-checked outcome, and before the scope's first run
    answer_id: uuid.UUID | None  # None until the outcome is answered
    label: GapLabel | None  # code's (app.csf.gap_label); None: not checked, not answered yet, not applicable
    explanation: str | None  # code's one paragraph; for Confirmed by you, the visitor's stored answer
    sources: int  # cited documents


class GapOut(BaseModel):
    scope: GapScope
    csf_version: str
    retrieved: str  # when NIST's text was downloaded
    controls_url: str  # NIST's SP 800-53 Rev 5 page; every related control links to it
    run: RunOut | None  # the latest run of the scope's current built-in questionnaire; None before the first
    rows: list[GapRow]  # every outcome of the scope's functions (the core: all of them), in NIST's order
```

`app/api/gap.py`, with the docstrings Task 3 keeps, so `openapi.json` does not move when the stubs are replaced:

```python
"""The CSF 2.0 gap check over HTTP (CSF spec 5.1, 7). Owner: lane 6B-api (Task 3); stubs until then."""

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import ERRORS, GapOut, GapScope, RunOut

router = APIRouter(tags=["gap"], responses=ERRORS)


@router.get("/api/gap/{scope}")
def gap_view(scope: GapScope, ws: WorkspaceDep, session: SessionDep) -> GapOut:
    """Every outcome of the scope's functions in NIST's order (the core: all 106), each with its tier and,
    once the latest run of the scope's current questionnaire has answered it, its gap label and explanation.
    Labels are decided by code; a not-checked outcome never carries one. Writes nothing; no model call."""
    raise HTTPException(501, "Not built yet.")


@router.post("/api/gap/{scope}/run")
def start_gap(scope: GapScope, ws: WorkspaceDep, session: SessionDep, request: Request) -> RunOut:
    """Start or continue the gap check for this scope, then call POST /api/runs/{id}/step while `running`.
    Creates (or reuses) the workspace's built-in questionnaire for the scope; it is never counted, listed or
    deleted with the visitor's questionnaires. Answers a new run when none exists on it, the running one, or
    the done one with every outcome whose evidence changed since (a new upload) re-opened, all of its parts; with
    nothing changed it stays done and no model is called. 429 per network (`run`, 20 an hour); 503 when the demo
    is full."""
    raise HTTPException(501, "Not built yet.")
```

In `app/main.py`, add `gap` to the `from app.api import ...` line and to the router loop:

```python
for module in (documents, questionnaires, runs, answers, questions, export, audit, gap):
    app.include_router(module.router)
```

- [ ] **Step 7: Regenerate, check the CONTROLS_URL page, run the chains**

Run: `python scripts/export_openapi.py && (cd web && npm run gen:api) && pytest tests/test_openapi.py -v && (cd web && npm run build)`
Expected: PASS. `api-types.ts` gains `GapOut`, `GapRow` and `PartOut`, `parts?: components["schemas"]["PartOut"][]` on `AnswerDetail`, and `part?: number` on `SuggestionOut`.

Lead only: open `https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final` in a browser (WebFetch) and confirm it is NIST's SP 800-53 Rev 5 publication page. If it moved, use the page it redirects to, and write that URL into Task 3 Step 3's `CONTROLS_URL` and into this step before the lanes start.

Then run the full backend chain.

- [ ] **Step 8: Write the contract lines in `docs/CONTRACTS.md`**

In the unit table's `csf` row, append to the public interface: `; current_mapping(scope) -> dict[str, str]; check_part(session, workspace_id, o, n, llm, models, spend) -> ItemResult; part_result(o, n, raw) -> ItemResult; CONTROLS_URL`.

Replace the HTTP section's "Plan 6B room" bullet with:

```markdown
- Gap check (Plan 6B): `GET /api/gap/{scope}` (`core` or one CSF function, lowercase) answers `GapOut`: every
  outcome of the scope's functions in NIST's order with its tier, and the label (`app.csf.gap_label`) and
  explanation from the latest run of the scope's current built-in questionnaire; it writes nothing.
  `POST /api/gap/{scope}/run` creates or reuses that questionnaire (Plan 3 Ruling 5: built-in ones are never
  counted, listed or deleted) and answers the run to step: a new one, the running one, or the done one with
  every outcome whose evidence changed re-opened in full (`app.runs.reopen_changed`, CSF spec 5.6; none
  changed: it stays done). It is counted under `run`, and 503 when the demo is full. A step claims csf items until their parts add up to
  `STEP_PARTS` (8) and stores each part's result in `run_items.parts` as it lands. `AnswerDetail.parts` lists a
  Checked outcome's parts; `SuggestionOut.part` names the part a fill is for (0: the whole item); on a gap-check
  run an answer is re-checked against the open parts in its CSF function. On a gap-check run,
  `GET /api/runs/{id}/export` answers the gap-report workbook (it was a 409), and Questions for you holds the
  Ask-me outcomes only. An xlsx questionnaire export carries the latest done gap check as a `Gap report` sheet.
  `Mapping.scope` stays unused.
```

Add to the change log:

```markdown
- 2026-10-06: Plan 6B Task 1 (added paths, optional fields and one status, allowed after the freeze; lead's OK
  under rule 10 for the `csf` row): `GET /api/gap/{scope}`, `POST /api/gap/{scope}/run`, `GapOut`, `GapRow`,
  `PartOut`, `AnswerDetail.parts`, `SuggestionOut.part`; a gap-check run's export is 200 (was 409); migration
  `c4e8a2d6f1b3` (`run_items.parts`, `suggestions.part`). The `csf` row gains `current_mapping`, `check_part`,
  `part_result` and `CONTROLS_URL`. No prompt or label changes, so nothing is re-recorded.
```

- [ ] **Step 9: Commit**

```bash
git add migrations/versions/c4e8a2d6f1b3_csf_parts.py app/db/models.py app/api/schemas.py app/api/gap.py app/main.py tests/test_models.py tests/test_openapi.py openapi.json web/src/lib/api-types.ts docs/CONTRACTS.md
git commit -m "feat(csf): Plan 6B contract additions and the per-part migration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 10 (lead): adversary checkpoint 1, then the lanes**

Dispatch Fable 5.1 on `main..plan6b` with this plan's Tasks 2-7 and the questions under "Review gates". Fix its findings in Part 0, regenerate the types, add change-log lines, and commit. Then create the three lane worktrees from `plan6b` (Execution notes).

---

### Task 2: The step runner answers a gap-check run part by part

**Lane:** api, worktree `VART-wt-6b-api`, database `vart_test_6b_api`. **Implementer:** Opus 5.5. **Reviewer:** Opus (budget, transactions, resume). **Eval key:** none.

**Files:**
- Modify: `app/csf.py` (`current_mapping`, `check_part`, `part_result`; `check_parts` and `questionnaire_for` reuse them), `app/runs.py`
- Modify: `tests/test_csf_parts.py`
- Create: `tests/test_runs_csf.py`

**Interfaces:**
- Consumes:
  - `app.csf.part_inputs`, `evidence`, `_without_draft`, `aggregate`, `framework()`, `Outcome.parts` (6A);
  - `app.pipeline.answer_retrieved`;
  - `app.runs._raw`, `_values`, `_no_nul`, `_retryable`, `_release`, `CostMeter`;
  - `RunItem.parts` (Task 1).
- Produces:
  - `csf.current_mapping(scope: str) -> dict[str, str]`
  - `csf.check_part(session, workspace_id, o: Outcome, n: int, llm, models, spend) -> ItemResult` (n is 1-based)
  - `csf.part_result(o: Outcome, n: int, raw: Mapping[str, Any]) -> ItemResult`
  - `runs.STEP_PARTS = 8`
  - `runs.ASK: dict[str, Any]` (an Ask-me outcome's row before the visitor answers it)
  - `runs.outcome_values(o: csf.Outcome, parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]`: an `answers` row's values, every key an `Answer` column
  - A stored part is `{"question": str, "stance_prompt": str, "model": str, "label", "value", "text", "citations", "dropped", "conflict", "scope_note", "confidence", "stances", "chunk_ids", "retrieval_dropped"}` (the judge, then the keys of `runs._raw`). A part an accepted fill wrote (Task 4) has `"statement_id": str` and no judge. `csf.part_result` ignores the extra keys.
  - `runs._is_current(o, n, raw, models) -> bool`: the part's wording, stance prompt and model are the deployed ones (or it was filled from the visitor's answer).

- [ ] **Step 1: Write the failing engine tests**

Append to `tests/test_csf_parts.py`, adding `json`, `from datetime import date` and `from app import runs` to its imports:

```python
def test_a_stored_part_rebuilds_to_the_same_decision_and_explanation() -> None:
    o = _outcome(4)
    parts = [_part(1, "covered"), _part(2, "documents_disagree"), _part(3, "not_met"), _part(4, "gap")]
    d = parts[1].decision
    assert d.conflict is not None  # a dated side survives the JSON round trip
    side = replace(d.conflict.sides[0], date=date(2026, 9, 15))
    parts[1] = replace(parts[1], decision=replace(d, conflict=replace(d.conflict, sides=(side, d.conflict.sides[1]))))
    stored = [json.loads(json.dumps({"question": q, **runs._raw(r)})) for q, r in zip(o.parts, parts, strict=True)]
    rebuilt = [csf.part_result(o, n, raw) for n, raw in enumerate(stored, 1)]
    assert [r.decision for r in rebuilt] == [r.decision for r in parts]
    assert [r.item for r in rebuilt] == list(csf.part_inputs(o))
    assert csf.aggregate(o, rebuilt).decision == csf.aggregate(o, parts).decision
    assert csf.aggregate(o, rebuilt).draft.text == csf.aggregate(o, parts).draft.text


def test_check_part_runs_one_part_alone(s: Session) -> None:
    ws = _incident_policy(s)
    llm = FakeLLM([_stance("yes")])
    r = csf.check_part(s, ws, _two_parts(), 2, llm, MODELS, spender(s, ws))
    assert [(q.step, q.item_id) for q in llm.requests] == [("stance", "RS.AN-03#2")]
    assert csf.part_label(r) == "covered"


def test_the_current_mapping_names_the_scope_and_its_data() -> None:
    m = csf.current_mapping("recover")
    assert (m["csf_version"], m["retrieved"], m["scope"]) == ("2.0", "2026-10-05", "recover")
    assert m["digest"] != csf.current_mapping("core")["digest"]
    with pytest.raises(ValueError, match="unknown scope"):
        csf.current_mapping("everything")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_csf_parts.py -k "rebuilds or one_part_alone or current_mapping" -v`
Expected: FAIL with `AttributeError: module 'app.csf' has no attribute 'part_result'` (and `check_part`, `current_mapping`).

- [ ] **Step 3: Write `current_mapping`, `check_part` and `part_result`**

In `app/csf.py`, add `from datetime import date` and `from typing import Any` to the imports. Add `Citation`, `Conflict`, `ConflictSide` and `Stance` to the `app.contracts` import. After `_digest`, add:

```python
def current_mapping(scope: str) -> dict[str, str]:
    """What names the built-in questionnaire for `scope` under the CSF data deployed now (CSF spec 6): the data
    version, its retrieval date, the scope and a digest of its items. ValueError for an unknown scope."""
    outcomes = in_scope(scope)
    fw = framework()
    return {"csf_version": fw.version, "retrieved": fw.retrieved, "scope": scope, "digest": _digest(outcomes)}
```

In `questionnaire_for`, replace the lines that build `fw` and `mapping` with:

```python
    outcomes = in_scope(scope)
    mapping = current_mapping(scope)
```

(`fw` is no longer used there; the rest of the function is unchanged.)

Replace `check_parts` with `check_part` plus a `check_parts` that calls it (the docstring of `check_parts` is unchanged):

```python
def check_part(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    n: int,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult:
    """Part `n` (1-based) of a Checked outcome through the ordinary pipeline, on documents only, its draft
    refused before anything is spent (CSF spec 5.2): one stance call when it has passages, none otherwise."""
    item = part_inputs(o)[n - 1]
    retrieval = evidence(session, workspace_id, item)
    return answer_retrieved(session, workspace_id, item, retrieval, llm, models, _without_draft(spend))


def check_parts(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> list[ItemResult]:
    """<keep the existing docstring>"""
    if o.tier == "not_checked":
        raise ValueError(f"{o.id} is {NOT_CHECKED}")
    return [check_part(session, workspace_id, o, n, llm, models, spend) for n in range(1, len(o.parts) + 1)]
```

After `check_parts`, add:

```python
def _cited(rows: Sequence[Mapping[str, Any]]) -> tuple[Citation, ...]:
    return tuple(Citation(**c) for c in rows)


def _side(s: Mapping[str, Any]) -> ConflictSide:
    return ConflictSide(s["stance"], _cited(s["citations"]), date.fromisoformat(s["date"]) if s["date"] else None)


def part_result(o: Outcome, n: int, raw: Mapping[str, Any]) -> ItemResult:
    """Part `n` rebuilt from its stored record with no model call (app.runs stores each part as it lands, CSF
    spec 5.7): what `aggregate`, `explain` and the inspector need. The passages are not rebuilt; their chunk
    ids stay in raw["chunk_ids"]."""
    c = raw["conflict"]
    conflict = None
    if c:
        first, second = (_side(s) for s in c["sides"])
        conflict = Conflict(c["rule"], (first, second))
    decision = Decision(
        raw["label"],
        raw["value"],
        _cited(raw["citations"]),
        tuple(Dropped(**d) for d in raw["dropped"]),
        conflict,
        raw["scope_note"],
        raw["confidence"],
    )
    return ItemResult(
        part_inputs(o)[n - 1],
        Retrieval((), tuple(Dropped(**d) for d in raw["retrieval_dropped"])),
        tuple(Stance(**s) for s in raw["stances"]),
        decision,
        Draft(raw["text"], "template"),
        0.0,
        0,
    )
```

- [ ] **Step 4: Run the engine tests**

Run: `pytest tests/test_csf_parts.py tests/test_csf_framework.py -v`
Expected: PASS. The 6A tests, including `test_a_changed_tier_list_gives_a_new_questionnaire`, still pass.

- [ ] **Step 5: Write the failing runner tests**

Create `tests/test_runs_csf.py`:

```python
import json
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app.contracts import BudgetExhausted
from app.db.models import Answer, Item, Run, RunItem
from app.llm.client import LLMRequest, LLMResult
from app.services import llm_budget
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _backups(s: Session):  # type: ignore[no-untyped-def]
    """A gap-check run over PR.DS-11 alone (four parts) with one policy line that every part retrieves."""
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="backup-policy.docx"), line_start=2, line_end=2, text=LINE)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    o = csf.framework().get("PR.DS-11")
    it = f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
    s.commit()
    return ws, it, runs.create_run(s, ws.id, q.id, MODELS)


def _parts_of(s: Session, run_id: object) -> RunItem:
    s.expire_all()
    return s.scalars(select(RunItem).where(RunItem.run_id == run_id)).one()


def test_a_gap_step_claims_outcomes_until_their_parts_add_up_to_eight(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "core")
    run = runs.create_run(s, ws.id, q.id, MODELS)
    llm = ByStepLLM({})  # no documents: no part has a passage, so a call would be a KeyError here
    weight = {o.id: max(1, len(o.parts)) for o in csf.in_scope("core")}
    first = runs.step(s, ws.id, run.id, llm, MODELS)
    # 1 + 1 + 1 + 3 parts; GV.PO-02's 4 would make 10
    assert [s.get_one(Item, i).csf_id for i in first] == ["GV.OC-03", "GV.RM-02", "GV.RR-02", "GV.PO-01"]
    steps = [first]
    while answered := runs.step(s, ws.id, run.id, llm, MODELS):
        steps.append(answered)
    for answered in steps:
        total = sum(weight[s.get_one(Item, i).csf_id or ""] for i in answered)
        assert total <= runs.STEP_PARTS or len(answered) == 1
    assert sum(len(a) for a in steps) == 36 and llm.requests == []
    ask = s.scalars(select(Answer).join(Item, Item.id == Answer.item_id).where(Item.csf_id == "GV.OC-03")).one()
    assert (ask.label, ask.text, ask.citations) == ("unknown", "", [])
    o = csf.framework().get("GV.OC-03")
    assert csf.gap_label(o, "unknown", None, ask.statement_id) == "not_answered"


def test_a_refused_budget_keeps_the_paid_parts_and_the_next_step_pays_only_the_rest(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, it, run = _backups(s)
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    llm = ByStepLLM({"stance": YES}, cost=0.001)
    with pytest.raises(BudgetExhausted):
        runs.step(s, ws.id, run.id, llm, MODELS)
    ri = _parts_of(s, run.id)
    assert (sorted(ri.parts), ri.state, ri.attempts) == (["1", "2"], "pending", 0)
    assert s.scalar(select(Answer).where(Answer.run_id == run.id)) is None  # no outcome row until it is whole
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]  # each part paid once
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.value, a.stances) == ("verified", "Yes", [])
    assert a.text.startswith("Evidenced: parts 1, 2, 3, 4.")
    assert a.chunk_ids == _parts_of(s, run.id).parts["1"]["chunk_ids"]  # the parts' union: one chunk here
    s.refresh(run)
    assert (run.status, float(run.cost_usd)) == ("done", pytest.approx(0.004))


def test_a_stored_part_with_other_wording_is_run_again(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = ByStepLLM({"stance": YES})
    runs.step(s, ws.id, run.id, llm, MODELS)
    stored = dict(_parts_of(s, run.id).parts)
    stored["2"] = {**stored["2"], "question": "Are backups of data kept somewhere safe?"}  # an older cut
    s.execute(delete(Answer).where(Answer.run_id == run.id))
    s.execute(update(RunItem).where(RunItem.run_id == run.id).values(parts=stored, state="pending"))
    s.execute(update(Run).where(Run.id == run.id).values(status="running", finished_at=None))
    s.commit()
    llm.requests.clear()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#2"]
    assert _parts_of(s, run.id).parts["2"]["question"] == csf.framework().get("PR.DS-11").parts[1]


def test_a_stored_part_judged_by_another_model_is_run_again(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = ByStepLLM({"stance": YES})
    runs.step(s, ws.id, run.id, llm, MODELS)
    stored = dict(_parts_of(s, run.id).parts)
    assert (stored["1"]["stance_prompt"], stored["1"]["model"]) == ("stance@p3", MODELS["stance"])
    stored["3"] = {**stored["3"], "model": "old/stance-model"}  # judged before a model change (adversary-1 M5)
    s.execute(delete(Answer).where(Answer.run_id == run.id))
    s.execute(update(RunItem).where(RunItem.run_id == run.id).values(parts=stored, state="pending"))
    s.execute(update(Run).where(Run.id == run.id).values(status="running", finished_at=None))
    s.commit()
    llm.requests.clear()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#3"]


def test_no_transaction_is_open_while_a_part_runs(s: Session) -> None:
    ws, it, run = _backups(s)

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.item_id} ran inside an open transaction"
            return super().complete(req)

    llm = Watching({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert len(llm.requests) == 4

```

The questionnaire path keeps its four items a step; `tests/test_runs.py::test_a_step_answers_at_most_four_items_and_the_run_finishes` already pins it.

- [ ] **Step 6: Run them to verify they fail**

Run: `pytest tests/test_runs_csf.py -v`
Expected: FAIL. `runs` has no `STEP_PARTS`, and a csf item still goes through `answer_item` (one stance call per outcome, with the outcome's question).

- [ ] **Step 7: Write the per-part runner**

In `app/runs.py`:
- add to the imports: `from functools import partial`; `from app import csf`; `Questionnaire` in the `app.db.models` import (already there); `Spend` (already imported from `app.contracts`);
- after `FAILED_TEXT`, add:

```python
STEP_PARTS = 8  # CSF spec 5.7: a gap-check step claims outcomes until their parts add up to 8 (8 x 15 s p90)
# An Ask-me outcome waits for the visitor (CSF spec 5.4): no retrieval, no call; gap_label shows Not answered.
ASK: dict[str, Any] = {"label": "unknown", "value": None, "text": "", "confidence": 0.0}
```

Replace `_claim` with:

```python
def _claim(
    session: Session, run_id: uuid.UUID, now: datetime, *, by_parts: bool = False
) -> list[tuple[uuid.UUID, int]]:
    """(item id, attempts before this claim), in questionnaire order; committed before any model call. A
    questionnaire step takes STEP_ITEMS items. A gap-check step takes outcomes until their parts add up to
    STEP_PARTS (CSF spec 5.7): an outcome with more is taken alone, and an Ask-me outcome counts one."""
    rows = list(
        session.execute(
            select(RunItem.item_id, RunItem.attempts, Item.csf_id)
            .join(Item, Item.id == RunItem.item_id)
            .where(
                RunItem.run_id == run_id,
                or_(
                    RunItem.state == "pending",
                    and_(RunItem.state == "claimed", RunItem.claimed_at < now - STALE),
                ),
            )
            .order_by(Item.position)
            .limit(STEP_PARTS if by_parts else STEP_ITEMS)
            .with_for_update(skip_locked=True, of=RunItem)
        ).all()
    )
    if by_parts:
        rows = _by_parts(rows)
    if rows:
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id.in_([r.item_id for r in rows]))
            .values(state="claimed", claimed_at=now, attempts=RunItem.attempts + 1)
        )
    session.commit()  # rows locked but not taken are free again
    return [(r.item_id, r.attempts) for r in rows]


def _by_parts(rows: list[Any]) -> list[Any]:
    taken: list[Any] = []
    total = 0
    for r in rows:
        weight = max(1, len(csf.framework().get(r.csf_id).parts))
        if taken and total + weight > STEP_PARTS:
            break
        taken.append(r)
        total += weight
    return taken
```

Replace `_answer` with `_once` plus an `_answer` that uses it:

```python
def _once[T](session: Session, call: Callable[[], T], can_retry: Callable[[], bool]) -> T:
    """`call`, and once more after a failed model call (a malformed reply rarely repeats). Never again on a
    missing recording or a refused budget, nor once `can_retry` says the step's deadline has passed."""
    try:
        return call()
    except (ReplayMiss, BudgetExhausted):
        raise
    except LLMError as exc:
        if not _retryable(exc) or not can_retry():
            raise
        session.rollback()
        return call()


def _answer(
    session: Session,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
    can_retry: Callable[[], bool] = lambda: True,
) -> ItemResult:
    """One questionnaire item, retried once on a failed model call (`_once`)."""
    return _once(session, partial(answer_item, session, workspace_id, item, llm, models, spend), can_retry)


def _is_current(o: csf.Outcome, n: int, raw: Mapping[str, Any], models: Mapping[str, str]) -> bool:
    """A stored part still stands for part n as deployed: the same wording, judged by the same stance prompt and
    model (adversary-1 M5). A part filled from the visitor's answer has no judge of its own; only its wording
    counts."""
    if not 1 <= n <= len(o.parts) or raw.get("question") != o.parts[n - 1]:
        return False
    judged = (raw.get("stance_prompt"), raw.get("model")) == (STANCE_PROMPT, models["stance"])
    return judged or bool(raw.get("statement_id"))


def _answer_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    row: Item,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
    can_retry: Callable[[], bool],
) -> dict[str, Any]:
    """One gap-check outcome (CSF spec 5.2-5.5, 5.7). Ask me: no retrieval and no call. Checked: every part
    not stored yet runs through the pipeline (each retried once, `_once`) and is stored the moment it lands, so
    a step refused by the budget mid-outcome resumes without paying again. A stored part whose wording, stance
    prompt or model differs from the deployed one runs again (`_is_current`). Then code combines the parts
    (`outcome_values`). Task 2b turns the part loop into concurrent part jobs."""
    # ponytail: an id NIST withdrew in a data refresh is a KeyError here; the step's crash path ends the item
    # at MAX_ATTEMPTS. A refresh changes the digest, so only a run started before the deploy can meet one.
    o = csf.framework().get(row.csf_id or "")
    if o.tier != "checked":
        return dict(ASK)
    have = session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == row.id)) or {}
    parts = {
        str(n): have[str(n)]
        for n in range(1, len(o.parts) + 1)
        if str(n) in have and _is_current(o, n, have[str(n)], models)
    }
    session.commit()  # no transaction stays open into the first model call
    for n, text in enumerate(o.parts, 1):
        if str(n) in parts:
            continue
        call = partial(csf.check_part, session, workspace_id, o, n, llm, models, spend)
        judged = {"question": text, "stance_prompt": STANCE_PROMPT, "model": models["stance"]}
        parts[str(n)] = _no_nul({**judged, **_raw(_once(session, call, can_retry))})
        session.execute(
            update(RunItem).where(RunItem.run_id == run_id, RunItem.item_id == row.id).values(parts=dict(parts))
        )
        session.commit()
    return outcome_values(o, parts)


def outcome_values(o: csf.Outcome, parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """A Checked outcome's answer row from its stored parts, all present (CSF spec 5.3): the label by `combine`,
    code's explanation, the parts' citations and drops. Its chunk ids are the parts' union, so a metadata
    override finds it (app.redecide decides it again part by part); it keeps no stances of its own."""
    raws = [parts[str(n)] for n in range(1, len(o.parts) + 1)]
    values = _values(csf.aggregate(o, [csf.part_result(o, n, r) for n, r in enumerate(raws, 1)]))
    values["chunk_ids"] = list(dict.fromkeys(c for r in raws for c in r["chunk_ids"]))
    return values
```

In `step`, compute the run's kind before the claim, and pass it:

```python
    by_parts = (
        session.scalar(select(Questionnaire.source).where(Questionnaire.id == run.questionnaire_id)) == "csf"
    )
    deadline = clock() + DEADLINE_S
    claimed = _claim(session, run_id, now or datetime.now(UTC), by_parts=by_parts)
```

Inside the `try:` of the item loop, replace the three lines that build `item` and `values` with:

```python
            row = session.get_one(Item, item_id)
            if row.csf_id is not None:
                values = _answer_outcome(
                    session, workspace_id, run_id, row, meter, models, spend, lambda: clock() <= deadline
                )
            else:
                item = ItemInput(str(row.id), row.question, row.topic)
                values = _values(
                    _answer(session, workspace_id, item, meter, models, spend, lambda: clock() <= deadline)
                )
```

Update the module docstring's second sentence to end with: "a gap-check step claims outcomes by their parts (CSF spec 5.7) and stores each part as it lands."

- [ ] **Step 8: Run the runner tests and the whole runner suite**

Run: `pytest tests/test_runs_csf.py tests/test_runs.py tests/test_api_runs.py tests/test_csf_parts.py -v`
Expected: PASS. The existing runner tests show the questionnaire path is unchanged.

- [ ] **Step 9: Run the backend chain and the eval replays**

Run: the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`
Expected: PASS, with no diff (`evals/gap.py` calls `check_outcome` → `check_parts` → `check_part`, which does the same calls in the same order).

- [ ] **Step 10: Commit**

```bash
git add app/csf.py app/runs.py tests/test_csf_parts.py tests/test_runs_csf.py
git commit -m "feat(csf): the step runner answers gap-check outcomes part by part and resumes paid parts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2b: Speed-up A — a step answers its claimed items at the same time

**Lane:** api (after Task 2, before Task 3). **Implementer:** Opus 5.5. **Reviewer:** Opus (threads, sessions, budget, outage and deadline semantics). **Eval key:** none.

**Files:**
- Modify: `app/runs.py` (`step` answers through a worker pool; Task 2's `_answer_outcome` becomes part jobs plus `_keep_current_parts`)
- Modify: `tests/test_runs.py` (one test's expected numbers, see Step 6), `tests/test_runs_csf.py` (Task 2's resume test no longer assumes which two parts were paid first)
- Create: `tests/test_runs_concurrent.py`
- Modify: `docs/CONTRACTS.md` (one change-log line)

**Interfaces:**
- Consumes:
  - from Task 2: `csf.check_part`, `outcome_values`, `ASK`, `STEP_PARTS`, `_once`, `_raw`, `_values`, `_no_nul`, `_claim(..., by_parts=)`;
  - existing: `spender` (its counters are already atomic: `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` per call, see `llm_budget.try_consume` and `ip_limits.bump`), `CostMeter`, `_release`, `_write`, `_add_cost`, `_provider_down`, `_retryable`.
- Produces:
  - `runs._session(engine) -> Session`: a worker's own session (tests patch it to watch each worker's transactions);
  - `runs._Done(values: dict[str, Any] | None, cost: float, error: Exception | None = None)`;
  - `runs.step(...)`: same signature and return type. It answers the claimed items concurrently and returns their ids in questionnaire order.

**What changes and what stays.**

Each claimed questionnaire item is one job, at most `STEP_ITEMS` (4) a step. Each missing part of a claimed gap-check outcome is one job, at most `STEP_PARTS` (8) parts a step. The jobs run in a `ThreadPoolExecutor` of `STEP_PARTS` workers. Each worker:
- opens its own `Session` on the step's engine, never sharing one across threads;
- builds its own spender (which spends before every call and commits at once, so no transaction is held across a call);
- wraps the client in its own `CostMeter`;
- returns a `_Done` with its cost, even when it fails.

A part job stores its part with one atomic `UPDATE run_items SET parts = parts || jsonb_build_object(n, part)`. Two parts of one outcome finishing together cannot lose each other.

Back on the request's thread, the step settles each claimed item in claim order:
1. **Writes.** Every answer that came back is written (one row per item; `ON CONFLICT DO NOTHING` keeps a repeated write a no-op), and every paid call is added to `runs.cost_usd`.
2. **Give-backs.** These items go back to pending with their attempt refunded:
   - a job that met a refused budget;
   - a job that met a missing recording;
   - a job the deadline kept from starting;
   - a retry the deadline cut.

   A job that met a provider outage goes back with its attempt kept, as today.
3. **Raises.** After everything is written, the step raises, in this order:
   - `ReplayMiss`;
   - a `llm_budget.Refused` naming the cap;
   - an unexpected error (that item stays claimed, its attempt counted);
   - `ModelsUnavailable` (503), only when nothing was answered.

The one change in behaviour: items that ran beside a refused or failed one are answered and written, where the sequential runner gave them back untried. They were already paid for, so nothing is spent twice.

Model calls carry no order: a recording key is the request's content, so the order in which workers call the model changes no key and no result. The evals do not use `step`, and replay byte-identical.

**Limits.**
- A step now takes about as long as its slowest item: p90 about 15 s for a questionnaire item (stance then draft), and about 15 s for 8 parts. That is far under `DEADLINE_S` (240 s) and Vercel's 300 s.
- Calls per run do not change; they arrive faster.
  - The per-workspace hourly caps (stance 150, draft 120) and the per-network 400 are counts per hour, so a run hits them at the same total as before.
  - A second run inside the same hour is now likelier, and the caps refuse it as they already would.
- Each worker opens its own Postgres connection (the engine uses `NullPool`): up to 9 per step request. Production reaches Neon through its pooled URL, which multiplexes them.

**Expected wall-clock**, measured in Task 7b Step 6 when the lead generates the sample snapshot live:
- a 64-item questionnaire takes about 3 minutes (16 steps of about 12 s), down from about 11;
- a core gap run (73 parts, about 12 steps of up to 8 parts at about 15 s) takes about 4 minutes, down from about 13.

- [ ] **Step 1: Write the failing concurrency tests**

`tests/test_runs_concurrent.py`:

```python
import json
import threading
import time
from collections.abc import Iterator

import httpx
import openai
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import csf, runs
from app.api.errors import ModelsUnavailable
from app.contracts import BudgetExhausted
from app.db.models import Answer, Item, LlmUsage, RunItem
from app.llm.client import LLMError, LLMRequest, LLMResult
from app.services import llm_budget
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
QUOTE = "Customer data at rest is encrypted with AES-256."
STANCE = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
DRAFT = json.dumps({"text": 'Yes. The crypto policy says "Customer data at rest is encrypted with AES-256."'})
LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})
PAUSE = 0.5  # seconds per model call


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


class Slow(ByStepLLM):
    """Every call takes PAUSE seconds; a question containing a marker can be made to fail."""

    def __init__(self, replies: dict[str, str | Exception], fail: str = "", error: Exception | None = None) -> None:
        super().__init__(replies, cost=0.01)
        self.fail, self.error = fail, error

    def complete(self, req: LLMRequest) -> LLMResult:
        time.sleep(PAUSE)
        if self.fail and self.fail in req.user and self.error is not None:
            with self._lock:
                self.requests.append(req)
            raise self.error
        return super().complete(req)


def _questionnaire(s: Session, n: int):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="crypto-policy.docx"), line_start=4, line_end=4, text=QUOTE)
    q = f.questionnaire(s, ws)
    for i in range(1, n + 1):
        f.item(s, q, position=i, row_ref=f"Q!C{i}", code=f"DS-{i:02d}", topic="Data Security",
               question=f"Is customer data encrypted at rest? (item {i})")
    s.commit()
    return ws, runs.create_run(s, ws.id, q.id, MODELS)


def _outage() -> LLMError:
    err = LLMError("stance: 503")
    err.__cause__ = openai.APIStatusError(
        "down", response=httpx.Response(503, request=httpx.Request("POST", "http://x")), body=None
    )
    return err


def test_four_items_take_about_a_quarter_of_the_sequential_time(s: Session) -> None:
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT})
    start = time.monotonic()
    answered = runs.step(s, ws.id, run.id, llm, MODELS)
    took = time.monotonic() - start
    assert len(answered) == 4 and len(llm.requests) == 8
    assert took < 2 * 2 * PAUSE  # sequential: 4 items x (stance + draft) = 8 x PAUSE; concurrent: about 2 x PAUSE
    positions = [s.get_one(Item, i).position for i in answered]
    assert positions == [1, 2, 3, 4]  # questionnaire order, whatever order the workers finished in
    s.refresh(run)
    assert float(run.cost_usd) == pytest.approx(0.08)  # every paid call counted once


def test_a_gap_outcomes_parts_run_at_once(s: Session) -> None:
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="backup-policy.docx"), line_start=2, line_end=2, text=LINE)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    o = csf.framework().get("PR.DS-11")
    it = f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
    s.commit()
    run = runs.create_run(s, ws.id, q.id, MODELS)
    llm = Slow({"stance": YES})
    start = time.monotonic()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert time.monotonic() - start < 2.5 * PAUSE  # four parts; sequential would be 4 x PAUSE
    assert sorted(r.item_id for r in llm.requests) == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]
    ri = s.scalars(select(RunItem).where(RunItem.run_id == run.id)).one()
    assert sorted(ri.parts) == ["1", "2", "3", "4"]  # no part lost to a concurrent write
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.value) == ("verified", "Yes")


def test_spending_is_exact_under_concurrency(s: Session, db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    ws = f.workspace(s)
    s.commit()
    allowed: list[bool] = []
    lock = threading.Lock()

    def spend_once() -> None:
        with Session(db) as own:
            ok = spender(own, ws.id, network="net-1")("stance")
        with lock:
            allowed.append(ok)

    threads = [threading.Thread(target=spend_once) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 10  # exactly the cap, never one more
    used = s.scalar(select(LlmUsage.calls).where(LlmUsage.workspace_id == ws.id, LlmUsage.kind == "stance"))
    assert used == 16  # every attempt counted once (a refusal still counts, as before)


def test_a_budget_refusal_mid_step_writes_what_was_paid_and_gives_the_rest_back(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT})
    with pytest.raises(BudgetExhausted) as err:
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert isinstance(err.value, llm_budget.Refused) and err.value.scope == "workspace"
    states = sorted(s.execute(select(RunItem.state, RunItem.attempts)).all())
    assert states == [("done", 1), ("done", 1), ("pending", 0), ("pending", 0)]  # refused items: attempt refunded
    assert s.scalar(select(func.count()).select_from(Answer)) == 2
    s.refresh(run)
    assert float(run.cost_usd) == pytest.approx(0.04)  # two items, stance and draft each
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    assert len(runs.step(s, ws.id, run.id, llm, MODELS)) == 2
    assert [r.step for r in llm.requests].count("stance") == 4  # no item's stance was paid twice


def test_an_outage_mid_step_writes_the_others_and_keeps_the_attempt_of_the_item_that_met_it(s: Session) -> None:
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT}, fail="(item 3)", error=_outage())
    answered = runs.step(s, ws.id, run.id, llm, MODELS)  # something was answered: no 503
    assert [s.get_one(Item, i).position for i in answered] == [1, 2, 4]
    item3 = s.execute(
        select(RunItem.state, RunItem.attempts).join(Item, Item.id == RunItem.item_id).where(Item.position == 3)
    ).one()
    assert tuple(item3) == ("pending", 1)  # given back untried-as-failed; the attempt it met stays counted
    assert s.scalar(select(func.count()).where(Answer.text == runs.FAILED_TEXT)) == 0


def test_an_outage_on_every_item_is_a_503_with_no_failed_answer(s: Session) -> None:
    ws, run = _questionnaire(s, 3)
    llm = Slow({"stance": _outage()})
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert s.scalars(select(Answer)).all() == []
    assert sorted(s.execute(select(RunItem.state, RunItem.attempts)).all()) == [("pending", 1)] * 3


def test_no_worker_holds_a_transaction_while_it_calls_a_model(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ws, run = _questionnaire(s, 4)
    mine = threading.local()
    real = runs._session

    def watched(engine):  # type: ignore[no-untyped-def]
        mine.session = real(engine)
        return mine.session

    monkeypatch.setattr(runs, "_session", watched)

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not mine.session.in_transaction(), f"{req.step} ran inside its worker's open transaction"
            assert not s.in_transaction(), "the request's session held a transaction during a call"
            return super().complete(req)

    llm = Watching({"stance": STANCE, "draft": DRAFT})
    assert len(runs.step(s, ws.id, run.id, llm, MODELS)) == 4
    assert len(llm.requests) == 8
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_runs_concurrent.py -v`
Expected: FAIL.
- The timing tests take the sequential time (`took` about 8 x PAUSE).
- The refusal test finds the items after the refusal given back untried: one `done`, not two.
- `runs._session` does not exist.

`test_spending_is_exact_under_concurrency` passes already. It pins that the counters are atomic, since `try_consume` and `bump` upsert with `RETURNING`; keep it as the guard.

- [ ] **Step 3: Write the worker pool**

In `app/runs.py`:
- add `from concurrent.futures import ThreadPoolExecutor` and `from dataclasses import dataclass`;
- add `from sqlalchemy import Engine, literal` (beside the existing imports) and `from sqlalchemy.dialects.postgresql import JSONB`.

Then replace Task 2's `_answer_outcome` and the item loop of `step` with:

```python
@dataclass
class _Done:
    """One job's result: the values to write (None for a part job, or on an error), its cost, its error."""

    values: dict[str, Any] | None
    cost: float
    error: Exception | None = None


def _session(engine: Engine) -> Session:
    """A worker's own session: a Session is never shared across threads (Task 2b)."""
    return Session(engine, expire_on_commit=False)


def _item_job(
    engine: Engine,
    workspace_id: uuid.UUID,
    item_id: uuid.UUID,
    llm: LLMClient,
    models: Mapping[str, str],
    network: str | None,
    can_retry: Callable[[], bool],
) -> _Done:
    """One questionnaire item on a worker thread: its own session, spender and cost meter."""
    meter = CostMeter(llm)
    try:
        with _session(engine) as s:
            row = s.get_one(Item, item_id)
            item = ItemInput(str(row.id), row.question, row.topic)
            s.commit()
            spend = spender(s, workspace_id, network=network)
            return _Done(_values(_answer(s, workspace_id, item, meter, models, spend, can_retry)), meter.take())
    except Exception as exc:  # reported to the request's thread with the cost it paid
        return _Done(None, meter.take(), exc)


def _part_job(
    engine: Engine,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    o: csf.Outcome,
    n: int,
    llm: LLMClient,
    models: Mapping[str, str],
    network: str | None,
    can_retry: Callable[[], bool],
) -> _Done:
    """One part of a gap-check outcome on a worker thread, stored the moment it lands (CSF spec 5.7) with one
    atomic `parts || {n: part}` update, so two parts of one outcome finishing together never lose each other."""
    meter = CostMeter(llm)
    try:
        with _session(engine) as s:
            spend = spender(s, workspace_id, network=network)
            r = _once(s, partial(csf.check_part, s, workspace_id, o, n, meter, models, spend), can_retry)
            judged = {"question": o.parts[n - 1], "stance_prompt": STANCE_PROMPT, "model": models["stance"]}
            part = _no_nul({**judged, **_raw(r)})
            s.execute(
                update(RunItem)
                .where(RunItem.run_id == run_id, RunItem.item_id == item_id)
                .values(parts=RunItem.parts.op("||")(func.jsonb_build_object(str(n), literal(part, JSONB))))
            )
            s.commit()
            return _Done(None, meter.take())
    except Exception as exc:
        return _Done(None, meter.take(), exc)


def _keep_current_parts(
    session: Session, run_id: uuid.UUID, item_id: uuid.UUID, o: csf.Outcome, models: Mapping[str, str]
) -> list[int]:
    """Drop stored parts that are not current (`_is_current`: wording, stance prompt, model; Review Focus 4,
    adversary-1 M5); return the parts still to run."""
    have = session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == item_id)) or {}
    keep = {k: v for k, v in have.items() if k.isdigit() and _is_current(o, int(k), v, models)}
    if keep != have:
        session.execute(
            update(RunItem).where(RunItem.run_id == run_id, RunItem.item_id == item_id).values(parts=keep)
        )
    return [n for n in range(1, len(o.parts) + 1) if str(n) not in keep]


def _run_all(
    jobs: dict[uuid.UUID, list[Callable[[], _Done]]], in_time: Callable[[], bool]
) -> dict[uuid.UUID, list[_Done | None]]:
    """Every job at once (at most STEP_PARTS); a job the pool would start after the deadline is not started
    (None). Results come back per item in the order the jobs were listed, whatever order they finished in."""

    def guarded(job: Callable[[], _Done]) -> _Done | None:
        return job() if in_time() else None

    flat = [(item_id, job) for item_id, listed in jobs.items() for job in listed]
    with ThreadPoolExecutor(max_workers=max(1, min(len(flat), STEP_PARTS))) as pool:
        futures = [(item_id, pool.submit(guarded, job)) for item_id, job in flat]
    out: dict[uuid.UUID, list[_Done | None]] = {item_id: [] for item_id in jobs}
    for item_id, fut in futures:
        out[item_id].append(fut.result())
    return out


_WORST = (ReplayMiss, BudgetExhausted)  # an item's errors, most decisive first; then outage, then the rest


def _worst(errors: list[Exception]) -> Exception:
    for kind in _WORST:
        for e in errors:
            if isinstance(e, kind):
                return e
    for e in errors:
        if isinstance(e, LLMError) and _provider_down(e):
            return e
    return errors[0]
```

Rewrite `step`'s body after the claim. Its signature, its run check, `by_parts`, `deadline` and `_claim` stay as Task 2 wrote them:

```python
    claimed = _claim(session, run_id, now or datetime.now(UTC), by_parts=by_parts)
    engine = session.get_bind()
    assert isinstance(engine, Engine)

    def in_time() -> bool:
        return clock() <= deadline

    jobs: dict[uuid.UUID, list[Callable[[], _Done]]] = {}
    ready: dict[uuid.UUID, dict[str, Any]] = {}  # answered with no model call
    outcomes: dict[uuid.UUID, csf.Outcome] = {}
    for n, (item_id, attempts) in enumerate(claimed):
        try:
            if attempts >= MAX_ATTEMPTS:
                ready[item_id] = FAILED
                continue
            row = session.get_one(Item, item_id)
            if row.csf_id is None:
                jobs[item_id] = [partial(_item_job, engine, workspace_id, item_id, llm, models, network, in_time)]
                continue
            # ponytail: an id NIST withdrew in a data refresh is a KeyError here; the crash path below ends the
            # item at MAX_ATTEMPTS. A refresh changes the digest, so only a run started before the deploy meets one.
            o = csf.framework().get(row.csf_id)
            if o.tier != "checked":
                ready[item_id] = dict(ASK)
                continue
            outcomes[item_id] = o
            jobs[item_id] = [
                partial(_part_job, engine, workspace_id, run_id, item_id, o, k, llm, models, network, in_time)
                for k in _keep_current_parts(session, run_id, item_id, o, models)
            ]
        except Exception:
            _keep_cost(session, run_id, 0.0, claimed[n + 1 :])  # this item stays claimed; the rest go back
            raise
    session.commit()  # the request's session holds no transaction while the workers call models
    results = _run_all(jobs, in_time)

    answered: list[uuid.UUID] = []
    give_back: list[uuid.UUID] = []
    keep_attempt: list[uuid.UUID] = []
    replay: ReplayMiss | None = None
    refused: BudgetExhausted | None = None
    crashed: Exception | None = None
    for n, (item_id, _) in enumerate(claimed):
        if item_id in ready:
            _write(session, workspace_id, run_id, item_id, ready[item_id], 0.0)
            answered.append(item_id)
            continue
        done = results.get(item_id, [])
        cost = sum(d.cost for d in done if d is not None)
        errors = [d.error for d in done if d is not None and d.error is not None]
        if not errors and None not in done:
            values = (
                outcome_values(outcomes[item_id], _stored(session, run_id, item_id))
                if item_id in outcomes
                else done[0].values  # type: ignore[union-attr]
            )
            try:
                _safe_write(session, workspace_id, run_id, item_id, values or FAILED, cost)
            except Exception:
                rest = sum(d.cost for i, _ in claimed[n + 1 :] for d in results.get(i, []) if d is not None)
                _keep_cost(session, run_id, cost + rest, claimed[n + 1 :])
                raise
            answered.append(item_id)
            continue
        _add_cost(session, run_id, cost)
        session.commit()
        if not errors:  # the deadline kept a job from starting
            give_back.append(item_id)
            continue
        err = _worst(errors)
        if isinstance(err, ReplayMiss):
            replay = replay or err
            give_back.append(item_id)
        elif isinstance(err, BudgetExhausted):
            refused = refused or err
            give_back.append(item_id)
        elif isinstance(err, LLMError) and _provider_down(err):
            keep_attempt.append(item_id)  # an item the provider always fails still ends FAILED (adversary-3 N1)
        elif isinstance(err, LLMError) and _retryable(err) and not in_time():
            give_back.append(item_id)  # the deadline cut the retry: not tried twice, so not failed
        elif isinstance(err, (LLMError, SQLAlchemyError)):
            if isinstance(err, SQLAlchemyError):  # the type only: parameters carry the question's words
                log.error("run %s item %s: %s; answered as failed", run_id, item_id, type(err).__name__)
            _write(session, workspace_id, run_id, item_id, FAILED, 0.0)  # its cost is already added
            answered.append(item_id)
        else:
            crashed = crashed or err  # stays claimed with its attempt counted: a crash loop ends at MAX_ATTEMPTS
    _release(session, run_id, give_back)
    _release(session, run_id, keep_attempt, refund=False)
    if replay is not None:
        raise replay
    if refused is not None:
        kind = str(refused.args[0]) if refused.args else "stance"
        scope = (
            refused.scope if isinstance(refused, Refused) else refusal_scope(session, workspace_id, kind, network)
        )
        raise Refused(kind, scope) from None
    if crashed is not None:
        raise crashed
    if keep_attempt and not answered:
        raise ModelsUnavailable()  # the next step meets the outage itself when something was answered
    _finish_if_done(session, run)
    return answered
```

And the two helpers it uses:

```python
def _stored(session: Session, run_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
    parts: dict[str, Any] = session.scalar(
        select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == item_id)
    ) or {}
    return parts


def _safe_write(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    values: dict[str, Any],
    cost: float,
) -> None:
    """The database refused a value: write the failure, not a reclaim loop (as before)."""
    try:
        _write(session, workspace_id, run_id, item_id, values, cost)
    except DataError as exc:
        session.rollback()
        log.error("run %s item %s: %s on write; answered as failed", run_id, item_id, type(exc).__name__)
        _write(session, workspace_id, run_id, item_id, FAILED, cost)
```

`_answer`, `_once`, `_is_current`, `_write`, `_release`, `_keep_cost`, `_add_cost`, `CostMeter`, `outcome_values` and `_claim` stay. Delete Task 2's `_answer_outcome`: the part jobs and `_keep_current_parts` replace it.

Adversary-1 M3 (no deadline check between an outcome's parts) has no separate fix here. Every part job is guarded by `in_time()` when it starts. All of a claim's parts (at most 8) start together, so no part waits behind another outcome's slow parts.

Replace the docstring of `step` with:

```python
    """Answer the claimed items at once (Task 2b): up to STEP_ITEMS questionnaire items, or up to STEP_PARTS parts
    of gap-check outcomes, each job on a worker thread with its own session, spender and cost meter, spending
    before its model call and holding no transaction across it. Then, on this thread in claim order: write every
    answer that came back (one row per item; a duplicate write does nothing), count every paid call, and give
    back the items that met a refusal, a missing recording, the deadline or an outage (an outage keeps the
    attempt). Raises ReplayMiss, then a `llm_budget.Refused` naming the cap, then an unexpected error, then
    ModelsUnavailable when nothing was answered, always after the rest is written. Returns the item ids
    answered, in questionnaire order. `network` is `errors.network(request)`: each worker's spender counts
    each call."""
```

- [ ] **Step 4: Run the new tests**

Run: `pytest tests/test_runs_concurrent.py -v`
Expected: PASS.

- [ ] **Step 5: Run the runner suites to see what moved**

Run: `pytest tests/test_runs.py tests/test_runs_csf.py tests/test_api_runs.py -v`
Expected: every test passes except two. Both encode the sequential order, not a guarantee:
1. `test_a_provider_outage_writes_no_failed_answers`. Its three items now all start, and each meets the outage:
   - `len(llm.requests) == calls` becomes `3 * calls`;
   - the attempts become `[("pending", 1)] * 3`.

   Its guarantees hold: no failed answer, the cost is kept, a 503, and every item that met the outage keeps its attempt.
2. Task 2's `test_a_refused_budget_keeps_the_paid_parts_and_the_next_step_pays_only_the_rest`. Its four parts start together, so the two paid ones are any two:
   - `sorted(ri.parts) == ["1", "2"]` becomes `len(ri.parts) == 2`;
   - the request check becomes `sorted(q.item_id for q in llm.requests) == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]`. Each part is still paid exactly once.

Every other test in `tests/test_runs.py` passes unchanged:
- the deadline tests: each job reads the clock once when it starts and once before a retry, and `next()` on a list iterator is atomic;
- the refused-budget and network-limit tests, because exactly one call fits the cap;
- the cost, crash and database-error tests.

If any other test fails, that is a behaviour change: stop and report it, do not edit the test.

- [ ] **Step 6: Make exactly those two edits**

In `tests/test_runs.py`, `test_a_provider_outage_writes_no_failed_answers`:

```python
    assert len(llm.requests) == 3 * calls  # Task 2b: all three items start; each meets the outage
    assert s.scalars(select(Answer)).all() == []
    assert sorted(s.execute(select(RunItem.state, RunItem.attempts)).all()) == [("pending", 1)] * 3
```

with the comment line above the test extended by: `Task 2b: items run at once, so each item meets the outage and keeps its attempt.`

In `tests/test_runs_csf.py`, the two lines named in Step 5, with the comment `# Task 2b: parts start together, so the two paid parts are any two`.

Run: `pytest tests/test_runs.py tests/test_runs_csf.py tests/test_runs_concurrent.py tests/test_api_runs.py tests/test_csf_parts.py -v`
Expected: PASS.

- [ ] **Step 7: Add the contract line, run the chain and the replays**

Add to `docs/CONTRACTS.md`'s change log:

```markdown
- 2026-10-06: Plan 6B Task 2b (behaviour inside existing statuses; no path or field changed): a step answers its
  claimed items at once, each on its own session and spender. Items that ran beside a refused, outage-hit or
  missing-recording item are written, not given back (they were paid). The order of raises after the writes is
  ReplayMiss, a refused budget, an unexpected error, then the 503 when nothing was answered. Every item that met
  an outage keeps its attempt. The answers come back in questionnaire order.
```

Run: the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`.
Expected: PASS with no diff. The evals call `answer_item` and `check_outcome`, not `step`.

- [ ] **Step 8: Commit**

```bash
git add app/runs.py tests/test_runs.py tests/test_runs_csf.py tests/test_runs_concurrent.py docs/CONTRACTS.md
git commit -m "perf(runs): a step answers its claimed items and parts at once, each worker on its own session" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The gap endpoints, the inspector's parts and the gap sheet in both exports

**Lane:** api (after Task 2). **Implementer:** Sonnet 5.5. **Reviewer:** Sonnet (Opus looks at the exports' inert cells in checkpoint 2). **Eval key:** none.

**Files:**
- Modify: `app/csf.py` (`CONTROLS_URL`), `app/api/gap.py` (replace the stubs), `app/api/answers.py` (`_dropped`, `_parts`, `detail`), `app/export.py` (`GapSheet`, `gap_report`, `export_xlsx(..., gap=None)`), `app/api/export.py` (a gap-check run's report; the latest gap sheet in a questionnaire's xlsx)
- Create: `tests/test_api_gap.py`
- Modify: `tests/test_export.py`, `tests/test_api_errors.py` (the two gap paths move from `STUBS` to `COVERED`, Ruling 2), `docs/CONTRACTS.md` (one change-log line)

**Interfaces:**
- Consumes:
  - from Task 1: `GapOut`, `GapRow`, `PartOut`, `GapScope`;
  - from Task 2: `csf.current_mapping`, `csf.part_result`;
  - from 6A: `csf.questionnaire_for`, `csf.gap_label`, `csf.part_label`, `csf.GAP_WORDS`, `csf.NOT_CHECKED`;
  - existing: `app.runs.create_run`, `app.api.runs.run_out`, `app.api.runs.summary`, `app.api.errors.limit`, `app.services.capacity.ensure_capacity`, `app.export._put`.
- Produces:
  - `csf.CONTROLS_URL: str`
  - `app.api.gap.latest_run(session, questionnaire_id) -> Run | None`
  - `app.api.gap.gap_rows(session, scope: str, q: Questionnaire | None, run: Run | None) -> list[GapRow]`
  - `app.api.gap.gap_sheet(session, q: Questionnaire, run: Run) -> GapSheet`
  - `app.api.gap.latest_gap(session, workspace_id) -> tuple[Questionnaire, Run] | None` (the latest *done* gap-check run)
  - `app.export.GapSheet(rows: list[GapRow], citations: dict[uuid.UUID, list[dict[str, Any]]], run_date: str, scope: str, version: str, controls_url: str, statement_docs: frozenset[str] = frozenset())` (frozen dataclass; `statement_docs` are the workspace's statement document ids, whose quotes the sheet marks "(your answer)", adversary-1 I3)
  - `app.api.gap.FAILED_SENTENCE` (the explanation of an outcome whose model call failed twice, adversary-1 M4)
  - consumes Task 1's fix-round field `GapRow.not_applicable: bool = False` (adversary-1 I1)
  - `app.export.gap_report(g: GapSheet) -> bytes`
  - `app.export.export_xlsx(original, mapping, rows, gap: GapSheet | None = None) -> bytes` (the existing function gains the optional last argument)
  - `app.export.REVIEW`, `FOOTER`, `GAP_SHEET = "Gap report"`, `GAP_HEAD`
  - The built `GET /api/gap/{scope}` and `POST /api/gap/{scope}/run` (Task 4 adds check again to the POST)

- [ ] **Step 1: Write the failing API tests**

Create `tests/test_api_gap.py`:

```python
import io
import json
import threading
import uuid
from datetime import timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app import csf
from app.api.deps import get_llm
from app.api.gap import FAILED_SENTENCE
from app.db.models import Answer, DocumentLine, Questionnaire, Run, Workspace
from app.export import FOOTER
from app.runs import FAILED_TEXT
from app.main import app
from app.services.ip_limits import LIMITS
from tests import factories as f
from tests.apiclient import visitor
from tests.fakes import ByStepLLM

LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})


def _finish(client: TestClient, run_id: str, llm: object) -> None:
    app.dependency_overrides[get_llm] = lambda: llm
    try:
        for _ in range(60):
            if client.get(f"/api/runs/{run_id}").json()["status"] != "running":
                return
            assert client.post(f"/api/runs/{run_id}/step").status_code == 200
        raise AssertionError("the run did not finish")
    finally:
        app.dependency_overrides.pop(get_llm, None)


def _policy(s: Session, ws_id: uuid.UUID, status: str = "final") -> None:
    """One stored policy line, as an upload leaves it (document, line, chunk)."""
    doc = f.document(s, s.get_one(Workspace, ws_id), filename="backup-policy.docx", status=status)
    s.add(DocumentLine(document_id=doc.id, n=1, text=LINE))
    f.chunk(s, doc, line_start=1, line_end=1, text=LINE)
    s.commit()


def test_the_view_lists_every_outcome_and_labels_only_what_was_checked(db: Engine) -> None:
    client, _ = visitor(db)
    before = client.get("/api/gap/core").json()
    assert before["run"] is None and len(before["rows"]) == 106
    assert {r["label"] for r in before["rows"]} == {None}
    tiers = [r["tier"] for r in before["rows"]]
    assert (tiers.count("checked"), tiers.count("ask"), tiers.count("not_checked")) == (31, 5, 70)
    assert before["rows"][0]["outcome"] == csf.framework().outcomes[0].outcome  # NIST's text, verbatim
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Questionnaire)) == 0  # the view writes nothing
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))  # no documents: no part has a passage, nothing is called
    after = client.get("/api/gap/core").json()
    rows = {r["csf_id"]: r for r in after["rows"]}
    assert (rows["PR.DS-11"]["label"], rows["PR.DS-11"]["explanation"]) == ("gap", "No evidence: parts 1, 2, 3, 4.")
    assert (rows["GV.RM-02"]["label"], rows["GV.RM-02"]["explanation"]) == ("not_answered", None)
    assert all(r["label"] is None and r["item_id"] is None for r in after["rows"] if r["tier"] == "not_checked")
    assert after["run"]["status"] == "done" and after["controls_url"] == csf.CONTROLS_URL


def test_a_function_scope_lists_its_own_outcomes_and_runs_only_them(db: Engine) -> None:
    client, _ = visitor(db)
    rows = client.get("/api/gap/recover").json()["rows"]
    assert {r["function"] for r in rows} == {"Recover"}
    assert client.post("/api/gap/recover/run").json()["total"] == 1  # RC.RP-01: Recover's one checked outcome
    assert client.get("/api/gap/everything").status_code == 422


def test_starting_twice_continues_the_same_run_and_the_questionnaire_stays_built_in(db: Engine) -> None:
    client, _ = visitor(db)
    first = client.post("/api/gap/core/run").json()
    again = client.post("/api/gap/core/run").json()
    assert (again["id"], again["status"]) == (first["id"], "running")
    assert client.get("/api/questionnaires").json() == []  # Plan 3 Ruling 5: never listed or counted


def test_starting_counts_under_the_run_limit(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(LIMITS, "run", (1, timedelta(hours=1)))
    client, _ = visitor(db)
    assert client.post("/api/gap/core/run").status_code == 200
    res = client.post("/api/gap/govern/run")
    assert res.status_code == 429 and res.headers["Retry-After"]


def test_another_workspace_sees_none_of_it(db: Engine) -> None:
    client, _ = visitor(db)
    client.post("/api/gap/core/run")
    other, _ = visitor(db)
    assert other.get("/api/gap/core").json()["run"] is None


def test_an_outcomes_evidence_lists_its_parts_with_their_own_citations(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        _policy(s, ws_id, status="draft")
    run = client.post("/api/gap/protect/run").json()
    _finish(client, run["id"], ByStepLLM({"stance": YES}))
    row = next(r for r in client.get("/api/gap/protect").json()["rows"] if r["csf_id"] == "PR.DS-11")
    assert row["label"] == "partly_covered"  # every part rests on a draft
    detail = client.get(f"/api/answers/{row['answer_id']}").json()
    parts = detail["parts"]
    assert [p["n"] for p in parts] == [1, 2, 3, 4]
    assert [p["question"] for p in parts] == list(csf.framework().get("PR.DS-11").parts)
    assert {p["label"] for p in parts} == {"partly_covered"} and not any(p["from_statement"] for p in parts)
    cite = parts[0]["citations"][0]
    assert (cite["quote"], cite["status"], cite["found_in_source"]) == (LINE, "draft", True)  # carry d


def test_the_gap_report_downloads_for_a_gap_run(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/recover/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    res = client.get(f"/api/runs/{run['id']}/export")
    assert res.status_code == 200
    assert res.headers["content-disposition"] == 'attachment; filename="csf-2.0-recover-gap-report.xlsx"'
    ws = openpyxl.load_workbook(io.BytesIO(res.content))["Gap report"]
    recover = [o for o in csf.framework().outcomes if o.function == "Recover"]
    assert [ws.cell(n, 1).value for n in range(3, 3 + len(recover))] == [o.id for o in recover]
    assert ws.cell(len(recover) + 4, 1).value == FOOTER
    done = client.get(f"/api/runs/{run['id']}").json()
    assert (ws["B1"].value, ws["C1"].value) == ("Scope: recover", f"Run date: {done['finished_at'][:10]}")


def test_two_first_presses_at_once_make_one_run(db: Engine) -> None:
    client, _ = visitor(db)
    other = TestClient(app)
    other.cookies.update(client.cookies)  # the same workspace, a second tab
    ids: list[str] = []
    lock = threading.Lock()

    def press(c: TestClient) -> None:
        run_id = c.post("/api/gap/recover/run").json()["id"]
        with lock:
            ids.append(run_id)

    threads = [threading.Thread(target=press, args=(c,)) for c in (client, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == 2 and len(set(ids)) == 1  # adversary-1 I2: one run, the same id in both answers
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Run)) == 1


def test_not_applicable_reads_as_such_on_both_tiers(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    for code in ("PR.DS-11", "GV.RM-02"):  # one Checked, one Ask-me outcome (adversary-1 I1)
        res = client.post(f"/api/answers/{rows[code]['answer_id']}/not-applicable", json={"reason": "We hold no such data."})
        assert res.status_code == 200
    after = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    for code in ("PR.DS-11", "GV.RM-02"):
        r = after[code]
        assert (r["not_applicable"], r["label"]) == (True, None)
        assert r["explanation"].startswith("Not applicable: We hold no such data.")
    assert client.get(f"/api/answers/{after['PR.DS-11']['answer_id']}").json()["parts"] == []  # adversary-1 M2
    ws = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{run['id']}/export").content))["Gap report"]
    words = {ws.cell(n, 1).value: ws.cell(n, 4).value for n in range(3, 109)}
    assert words["PR.DS-11"] == words["GV.RM-02"] == "Not applicable"


def test_a_failed_outcome_never_reads_gap(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/recover/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    with Session(db) as s:
        s.execute(update(Answer).where(Answer.run_id == uuid.UUID(run["id"])).values(text=FAILED_TEXT))
        s.commit()
    row = next(r for r in client.get("/api/gap/recover").json()["rows"] if r["csf_id"] == "RC.RP-01")
    assert (row["label"], row["explanation"]) == (None, FAILED_SENTENCE)  # adversary-1 M4


def test_a_questionnaire_export_carries_the_latest_gap_sheet_only_when_one_exists(db: Engine) -> None:
    client, _ = visitor(db)
    q = client.post("/api/questionnaires/sample/vsq-a").json()
    qrun = client.post(f"/api/questionnaires/{q['id']}/runs").json()  # no step needed: an empty run exports
    before = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{qrun['id']}/export").content))
    assert "Gap report" not in before.sheetnames  # no gap check yet: the export is unchanged
    gap = client.post("/api/gap/recover/run").json()
    _finish(client, gap["id"], ByStepLLM({}))
    after = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{qrun['id']}/export").content))
    assert after.sheetnames == [*before.sheetnames, "Gap report"]
    ws = after["Gap report"]
    assert (ws["A1"].value, ws["B1"].value) == ("Possible gap — review it", "Scope: recover")
    assert ws["A3"].value == "RC.RP-01" and ws["D3"].value == "Gap"
```

Append to `tests/test_export.py`, adding `from typing import Any`, `GapRow` to the `app.api.schemas` import and `FOOTER, GAP_HEAD, REVIEW, GapSheet, gap_report` to the `app.export` import:

```python
CONTROLS = "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final"


def _gap_row(
    csf_id: str, tier: Any, label: Any, explanation: str | None, answer_id: Any = None, na: bool = False
) -> GapRow:
    return GapRow(
        csf_id=csf_id,
        function="Protect",
        category="Data Security",
        outcome=f"NIST text of {csf_id}",
        related_controls=["CP-09"],
        source_url="https://csrc.nist.gov/projects/cybersecurity-framework/filters#/csf/filters",
        tier=tier,
        item_id=None,
        answer_id=answer_id,
        label=label,
        explanation=explanation,
        sources=1 if answer_id else 0,
        not_applicable=na,
    )


def test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells() -> None:
    aid = uuid.uuid4()
    cite = {"quote": "=cmd|' /C calc'!A0", "filename": "backup-policy.docx", "line_start": 2, "document_id": "d1"}
    said = {"quote": "We review it yearly.", "filename": "answer-002.txt", "line_start": 1, "document_id": "s1"}
    rows = [
        _gap_row("PR.DS-11", "checked", "covered", "=SUM(A1)", aid),
        _gap_row("PR.DS-10", "not_checked", None, None),
        _gap_row("PR.DS-01", "checked", None, None),  # not answered yet
        _gap_row("PR.DS-02", "checked", None, "Not applicable: no transit", uuid.uuid4(), na=True),
    ]
    body = gap_report(
        GapSheet(rows, {aid: [cite, said]}, "2026-10-06", "core", "2.0", CONTROLS, frozenset({"s1"}))
    )
    ws = openpyxl.load_workbook(io.BytesIO(body))["Gap report"]
    assert ws["A1"].value == REVIEW == "Possible gap — review it"
    assert (ws["B1"].value, ws["C1"].value) == ("Scope: core", "Run date: 2026-10-06")
    assert tuple(c.value for c in ws[2]) == GAP_HEAD
    assert [ws.cell(n, 4).value for n in (3, 4, 5, 6)] == [
        "Covered", "Not checked in this version", "Not run yet", "Not applicable"  # adversary-1 I1
    ]
    assert (ws["E3"].value, ws["E3"].data_type) == ("=SUM(A1)", "s")
    assert (ws["F3"].value, ws["F3"].data_type) == (
        "\"=cmd|' /C calc'!A0\" (backup-policy.docx line 2); "
        "\"We review it yearly.\" (answer-002.txt line 1) (your answer)",  # adversary-1 I3
        "s",
    )
    assert (ws["G3"].value, ws["I3"].value, ws["J3"].value, ws["K3"].value) == (
        "NIST text of PR.DS-11", "CP-09", "2026-10-06", "2.0"
    )
    assert ws["H3"].value.endswith(CONTROLS)
    assert ws.cell(8, 1).value == FOOTER == "Not legal advice. CSF 2.0 text © NIST, public domain."


def test_a_questionnaire_xlsx_gains_the_gap_sheet_only_when_given_and_never_overwrites_a_sheet() -> None:
    original = (SAMPLES / "vsq-a.xlsx").read_bytes()
    plain = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, ROWS)))
    assert plain.sheetnames == openpyxl.load_workbook(io.BytesIO(original)).sheetnames  # no gap: unchanged
    gap = GapSheet([_gap_row("RC.RP-01", "checked", "gap", "=1+1", None)], {}, "2026-10-06", "recover", "2.0", CONTROLS)
    wb = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, ROWS, gap)))
    assert wb.sheetnames == [*plain.sheetnames, "Gap report"]
    assert wb.active.title == plain.active.title  # the visitor's sheet stays the one that opens
    ws = wb["Gap report"]
    assert (ws["B1"].value, ws["A3"].value) == ("Scope: recover", "RC.RP-01")
    assert (ws["E3"].value, ws["E3"].data_type) == ("=1+1", "s")
    taken = openpyxl.load_workbook(io.BytesIO(original))
    taken.create_sheet("Gap report")  # a visitor's own sheet of that name
    buf = io.BytesIO()
    taken.save(buf)
    names = openpyxl.load_workbook(io.BytesIO(export_xlsx(buf.getvalue(), VSQ, ROWS, gap))).sheetnames
    assert names[-2:] == ["Gap report", "Gap report (2)"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_api_gap.py tests/test_export.py -k "gap or outcome or scope or starting or workspace_sees or questionnaire or presses or applicable or failed" -v`
Expected: FAIL. The gap paths answer 501, `app.export` has no `GapSheet` or `gap_report`, `export_xlsx` takes no gap, and `AnswerDetail.parts` is `[]`.

- [ ] **Step 3: Write `CONTROLS_URL` and the endpoints**

In `app/csf.py`, after `NOT_CHECKED`:

```python
# NIST's SP 800-53 Rev 5 page. Every related control links here: no per-control page could be verified (the
# Reference Tool's deep links are single-page-app routes, 6A decision 3). The lead checked it (6B Task 1).
CONTROLS_URL = "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final"
```

Replace `app/api/gap.py`:

```python
"""The CSF 2.0 gap check over HTTP (CSF spec 5.1, 7). Owner: lane 6B-api (Tasks 3-4)."""

import uuid
from typing import cast

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import csf
from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import limit
from app.api.runs import run_out, summary
from app.api.schemas import ERRORS, GapOut, GapRow, GapScope, RunOut
from app.contracts import ItemLabel, Value
from app.db.models import Answer, Document, Item, Questionnaire, Run
from app.export import GapSheet
from app.runs import FAILED_TEXT, create_run
from app.services.capacity import ensure_capacity
from app.settings import get_settings

router = APIRouter(tags=["gap"], responses=ERRORS)
FAILED_SENTENCE = "Not checked: the model call failed twice. Press r to check again."


def latest_run(session: Session, questionnaire_id: uuid.UUID) -> Run | None:
    return session.scalar(
        select(Run)
        .where(Run.questionnaire_id == questionnaire_id)
        .order_by(Run.started_at.desc(), Run.id)
        .limit(1)
    )


def gap_rows(session: Session, scope: str, q: Questionnaire | None, run: Run | None) -> list[GapRow]:
    """Every outcome of the scope's functions in NIST's order, with the run's answer where it has one. The label
    is code's (`csf.gap_label`): none for a not-checked outcome, none before an outcome is answered, none for
    one marked not applicable (which sets `not_applicable`), none for one whose model call failed twice."""
    items = {} if q is None else {i.csf_id: i for i in session.scalars(select(Item).where(Item.questionnaire_id == q.id))}
    answers = (
        {}
        if run is None
        else {a.item_id: a for a in session.scalars(select(Answer).where(Answer.run_id == run.id))}
    )
    rows = []
    for o in csf.framework().outcomes:
        if scope != "core" and o.function.lower() != scope:
            continue
        item = items.get(o.id)
        a = answers.get(item.id) if item is not None else None
        label = (
            csf.gap_label(o, cast(ItemLabel, a.label), cast(Value | None, a.value), a.statement_id) if a else None
        )
        failed = a is not None and o.tier == "checked" and a.text == FAILED_TEXT
        na = a is not None and a.label == "na"
        if failed or na:
            label = None  # a model failure is not "no evidence" (M4); N/A is its own word on either tier (I1)
        rows.append(
            GapRow(
                csf_id=o.id,
                function=o.function,
                category=o.category,
                outcome=o.outcome,
                related_controls=list(o.related_controls),
                source_url=o.source_url,
                tier=o.tier,
                item_id=item.id if item is not None else None,
                answer_id=a.id if a else None,
                label=label,
                explanation=FAILED_SENTENCE if failed else (a.text or None) if a and (label or na) else None,
                sources=summary(a).sources if a and label else 0,
                not_applicable=na,  # adversary-1 I1: either tier; the reason is the explanation
            )
        )
    return rows


def gap_sheet(session: Session, q: Questionnaire, run: Run) -> GapSheet:
    """One gap-check run as a sheet (CSF spec 7): its rows, each answer's citations, its date, scope and the CSF
    data version it ran on (stored in the questionnaire's mapping)."""
    scope = q.mapping["scope"]
    cited = {a.id: a.citations for a in session.scalars(select(Answer).where(Answer.run_id == run.id))}
    statements = session.scalars(
        select(Document.id).where(Document.workspace_id == q.workspace_id, Document.kind == "statement")
    )
    return GapSheet(
        gap_rows(session, scope, q, run),
        cited,
        (run.finished_at or run.started_at).date().isoformat(),  # the last check, not the first (adversary-1 M6)
        scope,
        q.mapping["csf_version"],
        csf.CONTROLS_URL,
        frozenset(str(i) for i in statements),
    )


def latest_gap(session: Session, ws_id: uuid.UUID) -> tuple[Questionnaire, Run] | None:
    """The workspace's latest done gap-check run, any scope (plan 6B decision 5); None when there is none. A run
    being checked again is running, so its older sheet is not offered until it is done."""
    found = session.execute(
        select(Questionnaire, Run)
        .join(Run, Run.questionnaire_id == Questionnaire.id)
        .where(Questionnaire.workspace_id == ws_id, Questionnaire.source == "csf", Run.status == "done")
        .order_by(Run.started_at.desc(), Run.id)
        .limit(1)
    ).first()
    return (found[0], found[1]) if found else None


def _questionnaire(session: Session, ws_id: uuid.UUID, scope: str) -> Questionnaire | None:
    """The scope's built-in questionnaire under the CSF data deployed now, if a run ever made it."""
    return session.scalars(
        select(Questionnaire)
        .where(
            Questionnaire.workspace_id == ws_id,
            Questionnaire.source == "csf",
            Questionnaire.mapping.contains(csf.current_mapping(scope)),
        )
        .order_by(Questionnaire.created_at.desc())
    ).first()


@router.get("/api/gap/{scope}")
def gap_view(scope: GapScope, ws: WorkspaceDep, session: SessionDep) -> GapOut:
    """<the docstring of the committed stub in app/api/gap.py, unchanged (Ruling 2)>"""
    q = _questionnaire(session, ws.id, scope)
    run = latest_run(session, q.id) if q is not None else None
    fw = csf.framework()
    return GapOut(
        scope=scope,
        csf_version=fw.version,
        retrieved=fw.retrieved,
        controls_url=csf.CONTROLS_URL,
        run=run_out(session, run) if run is not None else None,
        rows=gap_rows(session, scope, q, run),
    )


@router.post("/api/gap/{scope}/run")
def start_gap(scope: GapScope, ws: WorkspaceDep, session: SessionDep, request: Request) -> RunOut:
    """<the docstring of the committed stub in app/api/gap.py, unchanged (Ruling 2)>"""
    ws_id = ws.id
    limit(request, session, "run")
    ensure_capacity(session)
    q = csf.questionnaire_for(session, ws_id, scope)  # commits
    # Two first presses at once (two tabs) must make one run, not two (adversary-1 I2): hold the questionnaire
    # row until the run exists. create_run's FOR SHARE on the same row is already ours.
    session.execute(select(Questionnaire.id).where(Questionnaire.id == q.id).with_for_update())
    run = latest_run(session, q.id)
    if run is None:
        run = create_run(session, ws_id, q.id, get_settings().models())  # commits: the lock ends here
    else:
        session.commit()
    return run_out(session, run)
```

In `tests/test_api_errors.py` (Ruling 2), empty `STUBS` and add the two gap paths to `COVERED`:

```python
STUBS: set[tuple[str, str]] = set()  # Plan 6B Task 3 built the gap stubs
```

```python
    ("/api/gap/{scope}", "get"): "tests.test_api_gap::test_the_view_lists_every_outcome_and_labels_only_what_was_checked",
    ("/api/gap/{scope}/run", "post"): "tests.test_api_gap::test_starting_twice_continues_the_same_run_and_the_questionnaire_stays_built_in",
```

Keep the docstrings exactly as the committed stubs in `app/api/gap.py` have them, so `openapi.json` does not move.

- [ ] **Step 4: Write the parts in the evidence**

In `app/api/answers.py`, add `from app import csf` and `from app.runs import FAILED_TEXT`, and import `PartOut` from the schemas and `RunItem` from the models. Replace the dropped loop in `detail` with a helper, and add `_parts`:

```python
def _dropped(session: SessionDep, d: dict) -> DroppedOut:  # type: ignore[type-arg]
    line = session.scalar(select(Chunk.line_start).where(Chunk.id == uuid.UUID(d["chunk_id"])))
    return DroppedOut(
        reason=d["reason"],
        document_id=uuid.UUID(d["document_id"]),
        filename=d["filename"],
        line=line,
        sentence=WHY[d["reason"]],
    )


def _parts(session: SessionDep, a: Answer, item: Item) -> list[PartOut]:
    """A Checked CSF outcome's parts as the runner stored them (CSF spec 5.2, carry d); [] for anything else,
    and [] for an outcome marked not applicable, a failed one, or one whose parts are not all stored: their
    documents may since have been deleted (adversary-1 M2)."""
    if item.csf_id is None or a.label == "na" or a.text == FAILED_TEXT:
        return []
    o = csf.framework().get(item.csf_id)
    stored = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id)) or {}
    )
    if len(stored) != len(o.parts):
        return []
    return [
        PartOut(
            n=int(k),
            question=raw["question"],
            label=csf.part_label(csf.part_result(o, int(k), raw)),
            citations=[_citation(session, c) for c in raw["citations"]],
            dropped=[_dropped(session, d) for d in raw["dropped"]],
            from_statement=raw.get("statement_id") is not None,
        )
        for k, raw in sorted(stored.items(), key=lambda kv: int(kv[0]))
        if int(k) <= len(o.parts)
    ]
```

In `detail`, use `dropped = [_dropped(session, d) for d in a.dropped]`, move `item = session.get_one(Item, a.item_id)` above the `return`, and pass `parts=_parts(session, a, item)` to `AnswerDetail`.

- [ ] **Step 5: Write the gap sheet, both exports and their endpoint**

In `app/export.py`, add `from app import csf`, and import `GapRow` next to `Mapping` from `app.api.schemas`. (`uuid`, `Any`, `dataclass`, `openpyxl` and `get_column_letter` are already imported.) Add this block above `export_xlsx`, whose new parameter names `GapSheet`:

```python
GAP_SHEET = "Gap report"
GAP_HEAD = (
    "ID", "Function", "Category", "Label", "Explanation", "Quotes", "NIST outcome", "Links", "Related controls",
    "Run date", "CSF version",
)  # CSF spec 7
REVIEW = "Possible gap — review it"
FOOTER = "Not legal advice. CSF 2.0 text © NIST, public domain."
NOT_RUN = "Not run yet"


@dataclass(frozen=True)
class GapSheet:
    """One gap-check run as a sheet (CSF spec 7): built by app.api.gap.gap_sheet, written by `_write_gap`."""

    rows: list[GapRow]
    citations: dict[uuid.UUID, list[dict[str, Any]]]
    run_date: str
    scope: str
    version: str
    controls_url: str
    statement_docs: frozenset[str] = frozenset()


def _gap_word(r: GapRow) -> str:
    if r.not_applicable:
        return LABEL_WORDS["na"]  # "Not applicable", on either tier (adversary-1 I1)
    if r.tier == "not_checked":
        return csf.NOT_CHECKED[0].upper() + csf.NOT_CHECKED[1:]  # "Not checked in this version"
    return csf.GAP_WORDS[r.label] if r.label else NOT_RUN


def _write_gap(ws: Any, g: GapSheet) -> None:
    """The review line with the scope and run date, a header, one row per outcome in scope (unchecked ones too,
    so coverage is never overstated), then the not-legal-advice footer. NIST's text is verbatim and every cell
    is inert text (`_put`)."""
    _put(ws.cell(1, 1), REVIEW)
    _put(ws.cell(1, 2), f"Scope: {g.scope}")
    _put(ws.cell(1, 3), f"Run date: {g.run_date}")
    for i, title in enumerate(GAP_HEAD, 1):
        _put(ws.cell(2, i), title)
    for n, r in enumerate(g.rows, 3):
        cited = g.citations.get(r.answer_id, []) if r.answer_id else []
        quotes = "; ".join(
            f'"{c["quote"]}" ({c["filename"]} line {c["line_start"]})'
            + (" (your answer)" if c.get("document_id") in g.statement_docs else "")  # adversary-1 I3
            for c in cited
        )
        cells = (
            r.csf_id, r.function, r.category, _gap_word(r), r.explanation, quotes or None, r.outcome,
            f"{r.source_url} {g.controls_url}", ", ".join(r.related_controls) or None, g.run_date, g.version,
        )
        for i, value in enumerate(cells, 1):
            _put(ws.cell(n, i), value)
    _put(ws.cell(len(g.rows) + 4, 1), FOOTER)
    for i, width in enumerate((10, 10, 28, 20, 60, 60, 60, 40, 20, 12, 10), 1):
        ws.column_dimensions[get_column_letter(i)].width = width


def _free_title(wb: Any, title: str) -> str:
    """A sheet name the visitor's workbook does not use yet: never overwrite their own sheet."""
    names, n, name = set(wb.sheetnames), 2, title
    while name in names:
        name, n = f"{title} ({n})", n + 1
    return name


def gap_report(g: GapSheet) -> bytes:
    """A gap-check run's own export: a workbook holding only the gap sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = GAP_SHEET
    _write_gap(ws, g)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
```

Give `export_xlsx` an optional last parameter `gap: GapSheet | None = None`. Add, just before its `out = io.BytesIO()`:

```python
    if gap is not None:  # plan 6B decision 5: the workspace's latest gap check rides along, after every sheet
        _write_gap(wb.create_sheet(_free_title(wb, GAP_SHEET)), gap)
```

`create_sheet` appends at the end and leaves the active sheet as it was.

In `app/api/export.py`, import `gap_sheet` and `latest_gap` from `app.api.gap`, and `gap_report` from `app.export`. In `export_run`, right after `q = session.get_one(Questionnaire, run.questionnaire_id)`:

```python
    if q.source == "csf":
        return _gap_report(session, ws.id, run, q)
```

Then pass the latest gap check into the xlsx branch. The csv branch is unchanged: a csv holds one table.

```python
    found = None if is_csv else latest_gap(session, ws.id)
    gap = gap_sheet(session, *found) if found else None
    body = export_csv(q.original_bytes, mapping, rows) if is_csv else export_xlsx(q.original_bytes, mapping, rows, gap)
```

This replaces the existing `body = (export_csv if is_csv else export_xlsx)(...)` line; compute `is_csv` before it, as now. Add `"gap": gap.scope if gap else None` to that audit record's `detail`, and add:

```python
def _gap_report(session: SessionDep, ws_id: uuid.UUID, run: Run, q: Questionnaire) -> Response:
    """A gap-check run's export (CSF spec 7): the gap-report workbook, named by the scope (a server value)."""
    g = gap_sheet(session, q, run)
    body = gap_report(g)
    audit_log.record(session, ws_id, "export", ref=str(run.id), detail={"rows": len(g.rows), "scope": g.scope})
    session.commit()
    return Response(
        body,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="csf-2.0-{g.scope}-gap-report.xlsx"'},
    )
```

Add two sentences to `export_run`'s docstring: "A gap-check run answers the gap-report workbook instead (CSF spec 7). An xlsx questionnaire's export also carries the workspace's latest done gap check as a `Gap report` sheet (renamed `Gap report (2)` and so on if the file has one), stating its scope and run date; a csv is unchanged." Then regenerate `openapi.json` and the types (the docstring is the operation's description). Add to `docs/CONTRACTS.md`'s change log:

```markdown
- 2026-10-06: Plan 6B Task 3 (an added sheet, no path, field or status changed): an xlsx questionnaire export
  carries the workspace's latest done gap check as a `Gap report` sheet (a free name when the file has one),
  every cell inert; with no done gap check, or for a csv, the export is unchanged (Tarun, 2026-10-06).
```

- [ ] **Step 6: Run the tests, the chain and the eval replays**

Run: `pytest tests/test_api_gap.py tests/test_export.py tests/test_api_runs.py tests/test_openapi.py -v`, then the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`
Expected: PASS, with no eval diff.

- [ ] **Step 7: Commit**

```bash
git add app/csf.py app/api/gap.py app/api/answers.py app/export.py app/api/export.py tests/test_api_gap.py tests/test_export.py openapi.json web/src/lib/api-types.ts docs/CONTRACTS.md
git commit -m "feat(csf): gap check endpoints, per-part evidence and the gap sheet in both exports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Check again, Ask-me questions, per-part fills in the same CSF function, per-part re-decide

**Lane:** api (after Task 3). **Implementer:** Opus 5.5. **Reviewer:** Opus (lock order, what survives a re-check, what an answer may fill, the `retrieve` change). **Eval key:** none.

Adversary checkpoint 1 (Ruling 4) shaped four parts of this task:
- **I3, Confirmed by you.** An accepted fill is the visitor's word, not a document's. The explanation names filled parts in their own group ("Confirmed by you: part 2."). The outcome reads Confirmed by you (`user_confirmed` with the statement) once every part that is not a Gap was filled from the visitor's answer. Not met and Documents disagree still win, because their parts are not filled. The gap sheet marks such quotes "(your answer)" (Task 3).
- **I4, Check again.**
  - A stored part is compared with today's retrieval as a set of passages, not an ordered list.
  - A Checked part's retrieval leaves statements out before its top 8, through the new optional `exclude_kinds` keyword on `app.retrieve.retrieve`. It is approved under rule 10, its default is unchanged, and it gets a CONTRACTS change-log line. So an Ask-me answer alone re-opens nothing.
  - Re-opening an outcome no longer dismisses its open per-part fills.
- **M1.** A stale accept on a re-opened outcome is a 409, not a 404.
- **M5.** A part judged by another stance prompt or model counts as changed (`runs._is_current`, Task 2).

**Files:**
- Modify:
  - `app/runs.py` (`reopen_changed`, `_same_evidence`; `outcome_values` gains the Confirmed-by-you rule);
  - `app/csf.py` (`explain` and `aggregate` take `filled`; `evidence` excludes statements from the top K);
  - `app/retrieve.py` (`exclude_kinds`, approved under rule 10);
  - `app/api/gap.py` (`start_gap`);
  - `app/questions.py` (`ensure_questions`, `_suggest`, `accept_suggestion`);
  - `app/api/questions.py` (`_suggestion_out`);
  - `app/redecide.py`;
  - `docs/CONTRACTS.md` (two change-log lines).
- Modify tests: `tests/test_runs_csf.py`, `tests/test_api_gap.py`, `tests/test_redecide.py`, `tests/test_retrieve.py`, `tests/test_csf_parts.py`.
- Create: `tests/test_questions_csf.py`.

**Interfaces:**
- Consumes:
  - from Task 2: `runs.outcome_values`, `csf.part_result`, `csf.part_inputs`, `csf.evidence`, and the stored part shape;
  - from Task 1: `SuggestedFill.part`;
  - existing: `app.interview.recheck` (unchanged, takes keyed `OpenItem`s), `app.redecide.passages_for`.
- Produces:
  - `runs.reopen_changed(session, workspace_id, run_id, models: Mapping[str, str] | None = None) -> int` (outcomes re-opened). `models` are today's judges; None means the run's own. The optional argument is added beside Task 1's recorded signature, with a change-log line.
  - `runs.REOPEN = ("verified", "partial", "conflict", "unknown")`
  - `questions._opens(session, run_id, item, answer) -> list[OpenItem]`
  - `questions._same_area(asked: Item, item: Item) -> bool` (a questionnaire: the same topic; a gap-check run: the same CSF function)
  - `questions._fill_part(session, sg, answer) -> None`
  - `redecide._redecide_parts(session, workspace_id, answer, parts) -> int`
  - `app.retrieve.retrieve(session, workspace_id, question, topic, *, exclude_kinds: tuple[str, ...] = ())`. Documents of those kinds never enter the candidates; the default changes nothing.
  - `csf.evidence(...)`: the top K comes from documents only. Statements a plain retrieval would have ranked are still reported as dropped, with reason `statement`.
  - `csf.explain(o, parts, filled: frozenset[int] = frozenset())` and `csf.aggregate(o, parts, filled: frozenset[int] = frozenset())`. With no `filled`, both give exactly 6A's output, so gap-dev replays unchanged.
  - `runs.outcome_values(o, parts)`: when at least one part is filled and every part that is not a Gap is filled, the outcome is `user_confirmed` with the first filled part's `statement_id`.
  - A filled part carries `"statement_id"` and is never re-decided or re-opened.
  - Lock order everywhere: answer, then run item, then question, then suggestions (as in `app/questions.py`).

- [ ] **Step 1: Write the failing check-again tests**

Append to `tests/test_runs_csf.py` (add `from datetime import UTC, datetime`):

```python
def _done(s: Session):  # type: ignore[no-untyped-def]
    ws, it, run = _backups(s)
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    return ws, it, run


def _stale(s: Session, run_id: object, part: str) -> None:
    """Make one stored part look judged on other passages (as before a new upload changed its retrieval)."""
    ri = _parts_of(s, run_id)
    ri.parts = {**ri.parts, part: {**ri.parts[part], "chunk_ids": []}}
    s.commit()


def test_check_again_with_nothing_changed_stays_done(s: Session) -> None:
    ws, it, run = _done(s)
    assert runs.reopen_changed(s, ws.id, run.id) == 0
    s.refresh(run)
    assert run.status == "done"
    assert s.scalars(select(Answer).where(Answer.run_id == run.id)).one().label == "verified"


def test_check_again_reruns_every_part_of_an_affected_outcome(s: Session) -> None:
    ws, it, run = _done(s)
    statement = f.document(s, ws, source="statement", kind="statement", filename="answer-001.txt")
    fill = f.suggestion(s, run, it, statement, part=2)  # an open per-part fill (adversary-1 I4 c)
    s.commit()
    _stale(s, run.id, "3")  # one part's evidence changed: the whole outcome is affected (CSF spec 5.6)
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # a second press re-opens nothing more
    s.refresh(run)
    ri = _parts_of(s, run.id)
    assert (run.status, ri.state, ri.parts) == ("running", "pending", {})
    assert s.scalar(select(Answer).where(Answer.run_id == run.id)) is None
    llm = ByStepLLM({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert sorted(q.item_id for q in llm.requests) == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]  # Task 2b: any order
    s.refresh(fill)
    assert fill.status == "open"  # a per-part fill survives the re-open; accepting it re-checks the part then


def test_the_same_passages_in_another_order_are_the_same_evidence(s: Session) -> None:
    ws, it, run = _backups(s)
    second = f.document(s, ws, filename="backup-schedule.docx")
    f.chunk(s, second, line_start=1, line_end=1, text="Backups of data are kept for thirty days.")
    s.commit()
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    ri = _parts_of(s, run.id)
    assert all(len(v["chunk_ids"]) == 2 for v in ri.parts.values())  # two passages, so order can differ
    ri.parts = {k: {**v, "chunk_ids": v["chunk_ids"][::-1]} for k, v in ri.parts.items()}
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # adversary-1 I4 a: compared as sets


def test_check_again_keeps_the_visitors_outcomes_and_accepted_parts(s: Session) -> None:
    ws, it, run = _done(s)
    _stale(s, run.id, "3")
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    a.approved_at = datetime.now(UTC)
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # approved: the visitor's
    a.approved_at = None
    s.commit()
    ri = _parts_of(s, run.id)
    ri.parts = {**ri.parts, "3": {**ri.parts["3"], "statement_id": str(uuid.uuid4())}}  # filled from an answer
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 0
```

(Add `import uuid` to the file's imports.)

Append to `tests/test_api_gap.py`:

```python
def test_check_again_after_an_upload_reopens_the_outcomes_the_new_document_reaches(db: Engine) -> None:
    client, ws_id = visitor(db)
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))  # no documents: every Checked outcome is Gap
    with Session(db) as s:
        _policy(s, ws_id)  # an upload
    llm = ByStepLLM({"stance": YES})
    again = client.post("/api/gap/core/run").json()
    assert (again["id"], again["status"]) == (run["id"], "running")
    reopened = {r["csf_id"] for r in client.get("/api/gap/core").json()["rows"] if r["tier"] == "checked" and r["answer_id"] is None}
    with Session(db) as s:  # exactly the outcomes whose parts now retrieve the new line (adversary-1 I4 d)
        new = {str(c) for c in s.scalars(select(Chunk.id).where(Chunk.workspace_id == ws_id))}
        reached = {
            o.id
            for o in csf.in_scope("core")
            if o.tier == "checked"
            and any(new & {p.chunk_id for p in csf.evidence(s, ws_id, part).passages} for part in csf.part_inputs(o))
        }
    assert reopened == reached and "PR.DS-11" in reached
    _finish(client, run["id"], llm)
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    assert rows["PR.DS-11"]["label"] == "covered"
    assert rows["GV.RM-02"]["label"] == "not_answered"  # Ask me is never re-checked
    calls = len(llm.requests)
    assert 4 <= calls <= 73  # every part with passages, of the outcomes the new line reaches
    assert client.post("/api/gap/core/run").json()["status"] == "done"  # nothing changed since
    assert len(llm.requests) == calls


def test_an_ask_me_answer_alone_reopens_nothing(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        _policy(s, ws_id)
    stance = ByStepLLM({"stance": YES})
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], stance)
    paid = len(stance.requests)
    question = next(q for q in client.get(f"/api/runs/{run['id']}/questions").json() if q["codes"] == ["GV.RM-02"])
    irrelevant = json.dumps({"passages": [{"passage": 1, "stance": "irrelevant", "quote": "", "note": "x"}]})
    app.dependency_overrides[get_llm] = lambda: ByStepLLM({"recheck": irrelevant})
    try:
        text = "Our risk appetite statement and our policy reviews are approved by the board each year."
        assert client.post(f"/api/questions/{question['id']}/answer", json={"text": text}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_llm, None)
    again = client.post("/api/gap/core/run").json()
    assert (again["id"], again["status"]) == (run["id"], "done")  # the statement takes no Checked part's slot
    assert len(stance.requests) == paid
```

Add `Chunk` to that file's `app.db.models` import.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_runs_csf.py tests/test_api_gap.py -k "check_again" -v`
Expected: FAIL. `runs` has no `reopen_changed`, the POST on a done run answers it unchanged, and a statement still takes a part's top-K slot.

- [ ] **Step 3: Write `reopen_changed` and wire it into the POST**

In `app/runs.py`, add `delete` to the `sqlalchemy` import and `SuggestedFill` to the models import, then:

```python
REOPEN = ("verified", "partial", "conflict", "unknown")  # machine labels; the visitor's own labels stay


def _same_evidence(
    session: Session,
    workspace_id: uuid.UUID,
    o: csf.Outcome,
    n: int,
    raw: Mapping[str, Any],
    models: Mapping[str, str],
) -> bool:
    """A stored part still describes the documents (retrieval only, no model call). It must have the deployed
    wording, stance prompt and model (`_is_current`), and the same passages retrieved now, compared as a set:
    the same passages in another order are the same evidence for decide (adversary-1 I4)."""
    if not _is_current(o, n, raw, models):
        return False
    found = csf.evidence(session, workspace_id, csf.part_inputs(o)[n - 1])
    return {p.chunk_id for p in found.passages} == set(raw["chunk_ids"])


def reopen_changed(
    session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, models: Mapping[str, str] | None = None
) -> int:
    """Check again after an upload (CSF spec 5.6; plan 6B decision 3), with no model call. A Checked outcome is
    affected when any stored part's evidence, wording or judge changed, or a part is missing. Every
    machine-judged part of an affected outcome is dropped, and the outcome goes back to pending with its answer
    removed and its whole-item fills dismissed, so the step loop runs all of its parts again. A part filled by a fill the visitor
    accepted stays, and so does an outcome the visitor edited, approved, confirmed or marked not applicable.
    Locks the run first, so two presses re-open once. Returns the outcomes re-opened; with any, the run is
    running again. Open per-part fills survive a re-open (adversary-1 I4): a fill is the visitor's statement
    judged against the part's wording, and accepting it later re-checks the part."""
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id).with_for_update())
    if run is None or run.status != "done":
        session.commit()
        return 0
    judges = models or run.models  # a part judged by another prompt or model re-opens (adversary-1 M5)
    rows = session.execute(
        select(Item, RunItem.parts)
        .join(RunItem, RunItem.item_id == Item.id)
        .join(Answer, (Answer.item_id == Item.id) & (Answer.run_id == run_id))
        .where(
            RunItem.run_id == run_id,
            Item.csf_id.is_not(None),
            Answer.label.in_(REOPEN),
            Answer.edited.is_(False),
            Answer.approved_at.is_(None),
        )
        .order_by(Item.position)
    ).tuples().all()  # fetched first: _same_evidence runs queries of its own
    reopened: dict[uuid.UUID, dict[str, Any]] = {}
    for item, stored in rows:
        o = csf.framework().get(item.csf_id or "")
        if o.tier != "checked":
            continue
        affected = len(stored) < len(o.parts) or any(
            not raw.get("statement_id") and not _same_evidence(session, workspace_id, o, int(k), raw, judges)
            for k, raw in stored.items()
        )
        if affected:  # every machine-judged part runs again; the visitor's accepted parts stay
            reopened[item.id] = {k: raw for k, raw in stored.items() if raw.get("statement_id")}
    for item_id, keep in reopened.items():  # lock order: answer, then run item, then suggestions
        session.execute(delete(Answer).where(Answer.run_id == run_id, Answer.item_id == item_id))
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id == item_id)
            .values(parts=keep, state="pending", claimed_at=None, attempts=0)
        )
        session.execute(
            update(SuggestedFill)
            .where(
                SuggestedFill.run_id == run_id,
                SuggestedFill.item_id == item_id,
                SuggestedFill.status == "open",
                SuggestedFill.part == 0,  # per-part fills stay open (adversary-1 I4 c)
            )
            .values(status="dismissed")
        )
    if reopened:
        run.status, run.finished_at = "running", None
        audit_log.record(session, workspace_id, "run.recheck", ref=str(run_id), detail={"outcomes": len(reopened)})
    session.commit()
    return len(reopened)
```

In `app/api/gap.py`, import `reopen_changed` from `app.runs`. In `start_gap`, replace the `if run is None:` block with:

```python
    if run is None:
        run = create_run(session, ws_id, q.id, get_settings().models())
    elif run.status == "done":
        reopen_changed(session, ws_id, run.id, get_settings().models())  # commits; nothing changed: stays done
        session.refresh(run)
```

- [ ] **Step 4: Run the check-again tests**

Run: `pytest tests/test_runs_csf.py tests/test_api_gap.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing interview and re-decide tests**

Create `tests/test_questions_csf.py`:

```python
import json
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app import questions as qs
from app.db.models import Answer, Item, RunItem, SuggestedFill
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/s", "draft": "m/d", "classify": "m/c", "recheck": "m/r", "judge": "m/j"}
TODAY = date(2026, 10, 6)
SAID = "Our cybersecurity policy is established and communicated to all staff."


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _core_done(s: Session):  # type: ignore[no-untyped-def]
    """A core gap run over no documents, done: every Checked outcome is Gap, every Ask-me one Not answered."""
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "core")
    run = runs.create_run(s, ws.id, q.id, MODELS)
    while runs.step(s, ws.id, run.id, ByStepLLM({}), MODELS):
        pass
    return ws, q, run


def _code(s: Session, item_ids: list) -> str:  # type: ignore[type-arg]
    return s.get_one(Item, item_ids[0]).csf_id or ""


def _item(s: Session, q_id: object, csf_id: str) -> Item:
    return s.scalars(select(Item).where(Item.questionnaire_id == q_id, Item.csf_id == csf_id)).one()


def _answer_id(s: Session, run_id: object, item_id: object) -> object:
    return s.scalar(select(Answer.id).where(Answer.run_id == run_id, Answer.item_id == item_id))


def test_a_gap_run_asks_its_ask_me_outcomes_only(s: Session) -> None:
    ws, q, run = _core_done(s)
    asked = sorted(_code(s, x.item_ids) for x in qs.ensure_questions(s, ws.id, run.id))
    assert asked == ["GV.OC-03", "GV.OV-01", "GV.RM-02", "GV.RR-02", "GV.SC-01"]  # no Checked Gap is a question


def test_an_ask_me_answer_is_redacted_stored_and_confirmed(s: Session) -> None:
    ws, q, run = _core_done(s)
    question = next(x for x in qs.ensure_questions(s, ws.id, run.id) if _code(s, x.item_ids) == "GV.RM-02")
    text = "Dana Ortiz signed our risk appetite statement, and it is shared at onboarding."
    _, answer, found = qs.answer_question(s, ws.id, question.id, text, None, MODELS, TODAY)
    assert answer is not None and found == []
    assert "Dana Ortiz" not in answer.text and "risk appetite statement" in answer.text
    o = csf.framework().get("GV.RM-02")
    assert csf.gap_label(o, answer.label, answer.value, answer.statement_id) == "confirmed_by_you"


def test_a_govern_answer_suggests_fills_for_govern_parts_only_until_accepted(s: Session) -> None:
    ws, q, run = _core_done(s)
    # GV.RM-02 (Risk Management Strategy) and GV.PO-01/02 (Policy) share only the CSF function Govern (decision 8)
    question = next(x for x in qs.ensure_questions(s, ws.id, run.id) if _code(s, x.item_ids) == "GV.RM-02")
    reply = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": SAID, "note": "x"}]})
    llm = ByStepLLM({"recheck": reply})
    _, _, found = qs.answer_question(s, ws.id, question.id, SAID, llm, MODELS, TODAY)
    po1, po2 = _item(s, q.id, "GV.PO-01"), _item(s, q.id, "GV.PO-02")
    # one re-check per open Govern part: GV.PO-01's 3 and GV.PO-02's 4, under MAX_RECHECKS; nothing else
    assert [r.item_id for r in llm.requests] == [f"{po1.id}#{n}" for n in (1, 2, 3)] + [
        f"{po2.id}#{n}" for n in (1, 2, 3, 4)
    ]
    assert len(llm.requests) <= qs.MAX_RECHECKS
    assert s.get_one(Answer, _answer_id(s, run.id, po1.id)).label == "unknown"  # nothing applied until accepted
    assert sorted((sg.item_id == po1.id, sg.part) for sg in found) == [
        (False, 1), (False, 2), (False, 3), (False, 4), (True, 1), (True, 2), (True, 3)
    ]
    fill = next(sg for sg in found if sg.item_id == po1.id and sg.part == 2)
    a = qs.accept_suggestion(s, ws.id, fill.id)
    # adversary-1 I3 (Ruling 4): the visitor's words never read as document evidence. Every part that is not a
    # Gap is filled from the answer, so the outcome reads Confirmed by you, citing the statement.
    assert (a.label, a.value, a.statement_id, a.approved_at) == ("user_confirmed", None, fill.statement_id, None)
    assert a.text.startswith("Confirmed by you: part 2. No evidence: parts 1, 3.")
    assert a.citations[0]["filename"] == "answer-002.txt"  # the visitor's statement (GV.RM-02 is item 2)
    assert csf.gap_label(csf.framework().get("GV.PO-01"), a.label, a.value, a.statement_id) == "confirmed_by_you"
    stored = s.scalars(select(RunItem).where(RunItem.run_id == run.id, RunItem.item_id == po1.id)).one().parts
    assert (stored["2"]["label"], stored["2"]["statement_id"]) == ("verified", str(fill.statement_id))
    states = dict(
        s.execute(select(SuggestedFill.part, SuggestedFill.status).where(SuggestedFill.item_id == po1.id)).tuples()
    )
    assert states == {1: "open", 2: "accepted", 3: "open"}  # only that part's other fills are dismissed
    with pytest.raises(qs.Conflict):
        qs.accept_suggestion(s, ws.id, fill.id)
    for n in (1, 3):  # the other parts' fills still apply to a confirmed outcome
        a = qs.accept_suggestion(s, ws.id, next(sg.id for sg in found if sg.item_id == po1.id and sg.part == n))
    assert (a.label, a.text.split(". ")[0]) == ("user_confirmed", "Confirmed by you: parts 1, 2, 3")


def test_a_stale_accept_on_a_re_opened_outcome_is_a_409(s: Session) -> None:
    ws, q, run = _core_done(s)
    question = next(x for x in qs.ensure_questions(s, ws.id, run.id) if _code(s, x.item_ids) == "GV.RM-02")
    reply = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": SAID, "note": "x"}]})
    _, _, found = qs.answer_question(s, ws.id, question.id, SAID, ByStepLLM({"recheck": reply}), MODELS, TODAY)
    po1 = _item(s, q.id, "GV.PO-01")
    s.execute(delete(Answer).where(Answer.run_id == run.id, Answer.item_id == po1.id))  # as reopen_changed does
    s.commit()
    with pytest.raises(qs.Conflict, match="being checked again"):  # adversary-1 M1: not the GONE 404
        qs.accept_suggestion(s, ws.id, next(sg.id for sg in found if sg.item_id == po1.id))


def test_an_answer_never_fills_another_functions_parts(s: Session) -> None:
    ws, q, run = _core_done(s)
    govern = [_item(s, q.id, c).id for c in ("GV.PO-01", "GV.PO-02")]
    s.execute(update(Answer).where(Answer.run_id == run.id, Answer.item_id.in_(govern)).values(approved_at=func.now()))
    s.commit()  # Govern has no open Checked part left; every other function's outcomes are open Gaps
    question = next(x for x in qs.ensure_questions(s, ws.id, run.id) if _code(s, x.item_ids) == "GV.RM-02")
    reply = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": SAID, "note": "x"}]})
    llm = ByStepLLM({"recheck": reply})
    _, answer, found = qs.answer_question(s, ws.id, question.id, SAID, llm, MODELS, TODAY)
    assert answer is not None and answer.label == "user_confirmed"
    assert (llm.requests, found) == ([], [])  # no Protect, Detect, Identify, Respond or Recover part is asked
```

Append to `tests/test_runs_csf.py`:

```python
def test_a_filled_part_never_makes_documents_read_covered(s: Session) -> None:
    ws, it, run = _done(s)
    o = csf.framework().get("PR.DS-11")
    parts = dict(_parts_of(s, run.id).parts)
    said = str(uuid.uuid4())
    parts["2"] = {**parts["2"], "statement_id": said}
    v = runs.outcome_values(o, parts)  # parts 1, 3, 4 Covered by the policy; part 2 filled
    assert (v["label"], v["value"]) == ("verified", "Yes")  # the documents still carry it
    assert v["text"].startswith("Confirmed by you: part 2. Evidenced: parts 1, 3, 4.")
    every = {k: {**p, "statement_id": said} for k, p in parts.items()}
    v = runs.outcome_values(o, every)
    assert (v["label"], v["value"], str(v["statement_id"])) == ("user_confirmed", None, said)
```

Append to `tests/test_csf_parts.py`:

```python
def test_with_no_fill_the_explanation_is_6a_s() -> None:
    o = _outcome(3)
    parts = [_part(1, "covered"), _part(2, "gap"), _part(3, "partly_covered")]
    assert csf.explain(o, parts, frozenset()) == csf.explain(o, parts)
    assert csf.explain(o, parts, frozenset({1})).startswith(
        "Confirmed by you: part 1. Partly evidenced: part 3. No evidence: part 2."
    )
```

Append to `tests/test_retrieve.py` (it has the `s` fixture, `f`, and imports `retrieve` from `app.retrieve`):

```python
def test_excluded_kinds_never_take_a_slot(s: Session) -> None:
    ws = f.workspace(s)
    policy = f.document(s, ws, filename="backup-policy.docx")
    f.chunk(s, policy, line_start=1, line_end=1, text="Backups of data are tested every quarter.")
    said = f.document(s, ws, filename="answer-001.txt", source="statement", kind="statement")
    f.chunk(s, said, line_start=1, line_end=1, text="Backups of data are tested and restored by our team.")
    s.commit()
    every = retrieve(s, ws.id, "Are backups of data tested?", None)
    docs_only = retrieve(s, ws.id, "Are backups of data tested?", None, exclude_kinds=("statement",))
    assert {p.doc.kind for p in every.passages} == {"policy", "statement"}  # the default is unchanged
    assert {p.doc.kind for p in docs_only.passages} == {"policy"}
```

Append to `tests/test_redecide.py` (add `from app import csf, runs`, `from app.db.models import RunItem` and `from tests.fakes import ByStepLLM`):

```python
def test_a_metadata_override_redecides_each_part_and_recombines(db: Engine) -> None:
    line = "Backups of data are created, protected, maintained and tested every day."
    yes = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": line, "note": "states it"}]})
    models = {"stance": "m/s", "draft": "m/d"}
    with Session(db) as s:
        ws = f.workspace(s)
        doc = f.document(s, ws, filename="backup-policy.docx")
        f.chunk(s, doc, line_start=2, line_end=2, text=line)
        q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
        o = csf.framework().get("PR.DS-11")
        f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
        s.commit()
        run = runs.create_run(s, ws.id, q.id, models)
        runs.step(s, ws.id, run.id, ByStepLLM({"stance": yes}), models)
        ri = s.scalars(select(RunItem).where(RunItem.run_id == run.id)).one()
        ri.parts = {**ri.parts, "4": {**ri.parts["4"], "statement_id": "00000000-0000-0000-0000-000000000001"}}
        doc.status = "draft"
        s.commit()
        assert redecide(s, ws.id, doc.id) == 1
        a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
        # decide over the outcome row's empty stances would say Gap; per part, a draft-only source is Partly
        assert (a.label, a.value) == ("partial", "Partial")
        assert a.text.startswith("Evidenced: part 4. Partly evidenced: parts 1, 2, 3.")
        s.expire_all()
        parts = s.scalars(select(RunItem).where(RunItem.run_id == run.id)).one().parts
        assert [parts[k]["label"] for k in "1234"] == ["partial", "partial", "partial", "verified"]
        assert all(parts[k]["stances"] for k in "123")  # each part keeps the stances it was judged with
```

- [ ] **Step 6: Run them to verify they fail**

Run: `pytest tests/test_questions_csf.py tests/test_redecide.py -v`
Expected: FAIL.
- The Checked Gap outcomes are queued as questions.
- An Ask-me answer re-checks nothing, because no Checked outcome shares its topic; or it re-checks per outcome.
- A filled part reads as document evidence.
- `explain` takes no `filled`, and `retrieve` takes no `exclude_kinds`.
- A stale accept is a 404.
- `redecide` turns the outcome into `unknown`.

- [ ] **Step 7: Write the interview changes**

In `app/questions.py`, add `from app import csf`, add `RunItem` to the models import, and import `outcome_values` from `app.runs`.

In `ensure_questions`, filter the pairs to what a person is asked:

```python
    pairs = [(i, a) for i, a in _open_pairs(session, run_id) if i.id not in asked and _ask_the_visitor(i)]
```

and add:

```python
def _ask_the_visitor(i: Item) -> bool:
    """A gap-check run asks only its Ask-me outcomes (CSF spec 5.4); a Checked finding is not a question."""
    return i.csf_id is None or csf.framework().get(i.csf_id).tier == "ask"


def _opens(session: Session, run_id: uuid.UUID, i: Item, a: Answer) -> list[OpenItem]:
    """What a statement can fill (spec 6.9): a questionnaire item as it is; a Checked outcome part by part, each
    open part (Gap, Partly covered, Documents disagree) as its own item keyed `<item id>#<n>` (CSF spec 5.6);
    an Ask-me outcome never (only the visitor answers it)."""
    if i.csf_id is None:
        return [OpenItem(ItemInput(str(i.id), i.question, i.topic), cast(ItemLabel, a.label))]
    o = csf.framework().get(i.csf_id)
    stored = session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == i.id)) or {}
    out = []
    for n, part in enumerate(csf.part_inputs(o), 1):
        raw = stored.get(str(n))
        if raw and raw.get("question") == part.question and raw["label"] in OPEN:
            out.append(OpenItem(ItemInput(f"{i.id}#{n}", part.question, part.topic), cast(ItemLabel, raw["label"])))
    return out
```

Add:

```python
def _same_area(asked: Item, i: Item) -> bool:
    """Which open items a statement may fill. A questionnaire keeps spec 6.9's rule: the answered item's topic.
    A gap-check run fills Checked parts in the answered outcome's CSF function (plan 6B decision 8: a Govern
    answer may fill Govern parts). Either way a fill is only a suggestion until the visitor accepts it."""
    if asked.csf_id is None or i.csf_id is None:
        return i.topic == asked.topic
    fw = csf.framework()
    return fw.get(i.csf_id).function == fw.get(asked.csf_id).function
```

In `_suggest`:
- Load the answered item first: `asked = session.get_one(Item, answered_item)`.
- In the `pairs` filter, replace `i.topic == topic` with `_same_area(asked, i)`.
- Replace the `opens = [...]` comprehension with:

```python
    opens = [o for i, a in pairs for o in _opens(session, run_id, i, a)][:MAX_RECHECKS]  # the per-answer cap
```

- `app.interview.recheck` is frozen and re-checks only the items of the one topic it is given. So replace its single call (inside the existing `try:`) with one call per topic group. The groups share the same `spend_in_time` (the 90 s deadline and the budget) and the same cost meter, so the cap of 8 calls per answer still holds:

```python
        found = [
            sg
            for t in dict.fromkeys(o.item.topic for o in opens)  # the topics in queue order
            for sg in recheck(
                session, workspace_id, statement_id, t, [o for o in opens if o.item.topic == t],
                meter, models["recheck"], spend_in_time,
            )
        ]
```

The `topic` parameter of `_suggest` stays as it is; the questionnaire path's groups hold one topic, which is that topic.

and in the `SuggestedFill` insert rows, replace `"item_id": uuid.UUID(sg.key),` with:

```python
                        "item_id": uuid.UUID(sg.key.partition("#")[0]),
                        "part": int(sg.key.partition("#")[2] or 0),
```

In `accept_suggestion`, replace the block that copies the fill into the answer (from `a.label, a.value, a.text, a.citations = ...` through `a.statement_id, a.approved_at, a.edited = ...`) with:

```python
    if sg.part:
        _fill_part(session, sg, a)
    else:
        a.label, a.value, a.text, a.citations = sg.label, sg.value, sg.text, sg.citations
        a.dropped, a.conflict, a.scope_note, a.confidence = sg.dropped, None, None, sg.confidence
        a.stances, a.chunk_ids, a.retrieval_dropped = [], [], []  # the run's stances describe the old answer (P7)
        a.statement_id, a.approved_at, a.edited = sg.statement_id, None, False
```

Add `SuggestedFill.part == sg.part` to the `where` of the update that dismisses the item's other open fills.

Add:

```python
def _fill_part(session: Session, sg: SuggestedFill, a: Answer) -> None:
    """Accept a fill for one part of a Checked outcome (CSF spec 5.6): it replaces that part's stored result,
    then the parts are combined and explained again; the outcome's answer is never replaced directly. Locks
    the run item after the answer (the lock order above)."""
    item = session.get_one(Item, sg.item_id)
    o = csf.framework().get(item.csf_id or "")
    ri = session.scalars(
        select(RunItem).where(RunItem.run_id == sg.run_id, RunItem.item_id == sg.item_id).with_for_update()
    ).one()
    raw = ri.parts.get(str(sg.part))
    if raw is None or raw["label"] not in OPEN or len(ri.parts) != len(o.parts):
        session.rollback()
        raise Conflict("This part was checked again since; the suggestion no longer applies.")
    parts = {
        **ri.parts,
        str(sg.part): {
            "question": raw["question"],
            "label": sg.label,
            "value": sg.value,
            "text": sg.text,
            "citations": sg.citations,
            "dropped": sg.dropped,
            "conflict": None,
            "scope_note": None,
            "confidence": sg.confidence,
            "stances": [],
            "chunk_ids": [],
            "retrieval_dropped": [],
            "statement_id": str(sg.statement_id),
        },
    }
    ri.parts = parts
    for key, value in outcome_values(o, parts).items():
        setattr(a, key, value)
    a.approved_at, a.edited = None, False
```

In `accept_suggestion`, read the answer so a re-opened outcome is a conflict, not a 404 (adversary-1 M1). Let a per-part fill still apply to an outcome that reads Confirmed by you (adversary-1 I3), and replace the `_still_open` check:

```python
    a = session.scalars(
        select(Answer).where(Answer.run_id == sg.run_id, Answer.item_id == sg.item_id).with_for_update()
    ).one_or_none()
    if a is None:
        session.rollback()
        raise Conflict("This outcome is being checked again; the suggestion no longer applies.")
```

```python
    confirmed_part = sg.part > 0 and a.label == "user_confirmed" and not a.edited and a.approved_at is None
    if not (_still_open(a) or confirmed_part):
        session.rollback()
        raise Conflict("This item was answered, edited or approved since; the suggestion no longer applies.")
```

In `app/api/questions.py`, `_suggestion_out` passes `part=s.part`.

**Confirmed by you (adversary-1 I3).** In `app/csf.py`, `explain` and `aggregate` take the filled part numbers. Change `explain`'s signature and its group lines:

```python
def explain(o: Outcome, parts: Sequence[ItemResult], filled: frozenset[int] = frozenset()) -> str:
    """<keep the existing docstring, adding:> Parts filled from the visitor's answer are named first, in their
    own group ("Confirmed by you: part 2."), never among the evidenced parts (adversary-1 I3)."""
    labels = [part_label(r) for r in parts]
    deciding = _DECIDING[combine(labels)]
    mine = [f"Confirmed by you: {_numbers(sorted(filled))}."] if filled else []
    groups = [
        f"{word}: {_numbers(ns)}."
        for label, word in PART_WORDS.items()
        if (ns := [n for n, x in enumerate(labels, 1) if x == label and n not in filled])
    ]
    answers = [
        f"{q} {template_answer(r.decision)}"
        for q, r, x in zip(o.parts, parts, labels, strict=True)
        if x in deciding
    ]
    return " ".join([*mine, *groups, *answers])
```

`aggregate(o, parts, filled: frozenset[int] = frozenset())` passes `filled` to `explain` and is otherwise unchanged. With no `filled`, both return exactly what they returned before (pinned by `test_with_no_fill_the_explanation_is_6a_s`; gap-dev replays unchanged).

In `app/runs.py`, `outcome_values` becomes:

```python
def outcome_values(o: csf.Outcome, parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """<keep the existing docstring, adding:> A part filled from the visitor's answer is named "Confirmed by you".
    When every part that is not a Gap was filled, the outcome is the visitor's: `user_confirmed` with the first
    filled part's statement, so it reads Confirmed by you and never Covered (adversary-1 I3, Ruling 4). A stated
    No or a disagreement on an unfilled part still decides the label."""
    raws = [parts[str(n)] for n in range(1, len(o.parts) + 1)]
    filled = frozenset(n for n, r in enumerate(raws, 1) if r.get("statement_id"))
    results = [csf.part_result(o, n, r) for n, r in enumerate(raws, 1)]
    values = _values(csf.aggregate(o, results, filled))
    values["chunk_ids"] = list(dict.fromkeys(c for r in raws for c in r["chunk_ids"]))
    rest = [n for n, r in enumerate(results, 1) if csf.part_label(r) != "gap"]
    if filled and all(n in filled for n in rest):
        said = uuid.UUID(raws[min(filled) - 1]["statement_id"])
        values.update(label="user_confirmed", value=None, statement_id=said)
    return values
```

`_write` inserts `statement_id` like any other column, and `ck_answers_statement` holds: a `user_confirmed` row always has its statement. A confirmed outcome is not `REOPEN`ed or re-decided (both select machine labels only), so the visitor's confirmation stands.

**Statements leave a Checked part's top K (adversary-1 I4 b; lead's OK under rule 10).** In `app/retrieve.py`, `retrieve` gains a keyword:

```python
def retrieve(
    session: Session, workspace_id: uuid.UUID, question: str, topic: str | None, *, exclude_kinds: tuple[str, ...] = ()
) -> Retrieval:
    """At most K passages for one questionnaire item, best first. Documents of a kind in `exclude_kinds` never
    become candidates (a CSF Checked part leaves out the visitor's statements; the default changes nothing)."""
```

Its candidate query passes `"exclude": list(exclude_kinds)`, and `_CANDIDATES`' `WHERE` gains `AND NOT (d.kind = ANY(CAST(:exclude AS text[])))`. An empty array makes that clause true, so every existing caller's query returns what it did. The IDF over the workspace (`_fused`) and the record hop are unchanged.

In `app/csf.py`, `evidence` keeps the statements out of the top K, and still reports the ones a plain retrieval would have ranked, so the inspector's "This is your own answer" line stays (6A's `test_a_checked_outcome_is_judged_on_documents_never_on_a_stored_answer` passes unchanged):

```python
def evidence(session: Session, workspace_id: uuid.UUID, item: ItemInput) -> Retrieval:
    """<keep the existing docstring, adding:> Statements never take one of the part's K slots (adversary-1 I4)."""
    r = retrieve(session, workspace_id, item.question, item.topic, exclude_kinds=("statement",))
    said = [p for p in retrieve(session, workspace_id, item.question, item.topic).passages if p.doc.kind == "statement"]
    return Retrieval(r.passages, r.dropped + tuple(Dropped(p.chunk_id, p.doc.id, p.doc.filename, "statement") for p in said))
```

`docs/CONTRACTS.md` already records the `retrieve` row with `exclude_kinds`, sets-of-passages, surviving per-part fills and the Confirmed-by-you rule (Part 0 fix round, `8542dc9`). Add only what it lacks: the `csf` row's `explain` and `aggregate` gain `filled=frozenset()`. Then add to the change log:

```markdown
- 2026-10-06: Plan 6B Task 4 (lead's OK under rule 10; adversary-1 I3, M5, Ruling 4): `csf.explain` and
  `csf.aggregate` gain `filled` (default empty: 6A's output); `runs.reopen_changed` gains an optional `models`
  (today's judges; a part judged by another stance prompt or model re-opens). No prompt or questionnaire label
  changes; nothing is re-recorded.
```

- [ ] **Step 8: Write the per-part re-decide**

In `app/redecide.py`, add `from app import csf`, `from app.runs import outcome_values`, `RunItem` and `Item` to the models import, and `update` to the `sqlalchemy` import. At the top of the loop in `redecide`:

```python
    for a in answers:
        parts = session.scalar(select(RunItem.parts).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id))
        if parts:  # a Checked CSF outcome: its row has no stances of its own (CSF spec 5.3)
            changed += _redecide_parts(session, workspace_id, a, parts)
            continue
```

and add:

```python
def _redecide_parts(session: Session, workspace_id: uuid.UUID, a: Answer, parts: dict[str, Any]) -> int:
    """A CSF outcome after a metadata override: each part decided again from its own stances and passages, then
    combined again (`outcome_values`). A part filled from the visitor's answer keeps its result. 1 when the
    outcome's label, value or citations changed (it then loses its approval), else 0."""
    o = csf.framework().get(session.get_one(Item, a.item_id).csf_id or "")
    new = dict(parts)
    for k, raw in parts.items():
        if raw.get("statement_id"):
            continue
        passages = passages_for(session, workspace_id, raw["chunk_ids"])
        if passages is None:
            continue
        d = decide(passages, tuple(Stance(**s) for s in raw["stances"]), _dropped(raw["retrieval_dropped"]))
        new[k] = {
            **raw,
            "label": d.label,
            "value": d.value,
            "citations": jsonable(d.citations),
            "dropped": jsonable(d.dropped),
            "conflict": jsonable(d.conflict),
            "scope_note": d.scope_note,
            "confidence": d.confidence,
            "text": template_answer(d),
        }
    if new == parts or len(new) != len(o.parts):
        return 0
    session.execute(update(RunItem).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id).values(parts=new))
    values = outcome_values(o, new)
    if (values["label"], values["value"], values["citations"]) == (a.label, a.value, a.citations):
        return 0
    for key, value in values.items():
        setattr(a, key, value)
    a.approved_at = None
    return 1
```

- [ ] **Step 9: Run the tests, the chain and the eval replays**

Run: `pytest tests/test_questions_csf.py tests/test_redecide.py tests/test_questions.py tests/test_runs_csf.py tests/test_api_gap.py tests/test_retrieve.py tests/test_csf_parts.py tests/test_csf_framework.py -v`, then the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`
Expected: PASS. The existing interview tests show that a questionnaire's fills (part 0) behave as before. The eval replays prove the `retrieve` default and the unfilled explanation are unchanged.

- [ ] **Step 10: Commit**

```bash
git add app/runs.py app/csf.py app/retrieve.py app/api/gap.py app/questions.py app/api/questions.py app/redecide.py docs/CONTRACTS.md tests/test_runs_csf.py tests/test_api_gap.py tests/test_redecide.py tests/test_retrieve.py tests/test_csf_parts.py tests/test_questions_csf.py
git commit -m "feat(csf): check again per affected outcome, Ask-me questions, per-part fills, Confirmed by you, re-decide" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The Gap check view (tab 6)

**Lane:** ui, worktree `VART-wt-6b-ui` (no database). **Implementer:** Opus 5.5. **Reviewer:** Opus (design.md, keys, accessibility). **Eval key:** none.

**Files:**
- Create: `web/src/views/GapCheck.tsx`, `web/src/views/GapCheck.test.tsx`
- Modify: `web/src/lib/api.ts`, `web/src/lib/route.ts`, `web/src/lib/route.test.ts`, `web/src/lib/labels.ts`, `web/src/components/ui.tsx`, `web/src/components/Shell.tsx`, `web/src/components/Shell.test.tsx`, `web/src/App.tsx`, `web/src/views/Export.tsx`, `web/src/views/Export.test.tsx`, `web/src/test/mockApi.ts`, `design.md`

**Interfaces:**
- Consumes:
  - from Task 1 (generated types): `GapOut`, `GapRow` (including the fix round's `not_applicable`, adversary-1 I1), `PartOut`;
  - existing: `useStepLoop(runId, data: RunRowsOut | null, onData, onGone)` from `RunGrid.tsx`, `Shell`, `Button`, `Kbd`, `ErrorLine`, `useKeys`, `go`, `goneOn404`;
  - the API: `GET /api/gap/{scope}`, `POST /api/gap/{scope}/run`, `POST /api/runs/{id}/step`, `GET /api/runs/{id}/export`.
- Produces:
  - in `api.ts`: types `GapOut`, `GapRow`, `PartOut`, `GapLabel`, `GapScope`; `api.gap(scope)`, `api.startGap(scope)`;
  - `route.ts`: view `"gap"` and route key `scope`;
  - `labels.ts`: `GAP_WORD`, `GAP_CHIP`, `GAP_LABELS`, `SCOPES`, `SCOPE_KEY`, `GAP_REVIEW`, `GAP_FOOTER`;
  - `ui.tsx`: `GapChip({ label })`;
  - `GapCheck({ workspace, onGone, scope?, outcome? })` and `coverage(rows: GapRow[]): string`;
  - `fixtures.gap` in `mockApi.ts` (four rows: GV.RM-02 ask not answered, PR.DS-11 covered, PR.DS-01 gap, PR.DS-10 not checked; run `r9` done 2 of 2).

design.md direction C: command line `workspace / csf 2.0 / <scope>` with the review line under it; a scope line with `g i p d s o a` toggles; the filter line with a count per gap label (covered, partly, not met, disagree, gap, confirmed by you, not answered, not checked); grouped 28px rows (`# protect / data security`); the coverage line in the status line; the footer under the list.

- [ ] **Step 1: Write the shared pieces and their tests**

`web/src/lib/api.ts`, next to the other aliases and in `api`:

```ts
export type GapOut = S["GapOut"];
export type GapRow = S["GapRow"];
export type PartOut = S["PartOut"];
export type GapLabel = NonNullable<GapRow["label"]>;
export type GapScope = GapOut["scope"];
```

```ts
  gap: (scope: GapScope) => request<GapOut>(`/api/gap/${scope}`),
  startGap: (scope: GapScope) => send<RunOut>(`/api/gap/${scope}/run`, "POST"),
```

`web/src/lib/route.ts`: `View` and `VIEWS` gain `"gap"`; `Route` gains `scope?: string`; `KEYS` becomes `["run", "item", "questionnaire", "scope"] as const`.

`web/src/lib/labels.ts` (import `GapLabel` and `GapScope` from `./api`):

```ts
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
```

`web/src/components/ui.tsx`: move LabelChip's classes into `const CHIP_BASE = "inline-block min-w-[9ch] px-1 text-center text-xs font-medium leading-[18px]";`, have `LabelChip` use `${CHIP_BASE} ${CHIP[label]}`, and add:

```tsx
export function GapChip({ label }: { label: GapLabel }) {
  return <span className={`${CHIP_BASE} ${GAP_CHIP[label]}`}>{GAP_WORD[label]}</span>;
}
```

`web/src/components/Shell.tsx`:
- `VIEWS` gains `["gap", "gap check"]`.
- `target` opens the gap view without a run: `v === "workspace" || v === "audit" || v === "gap" ? { view: v } : ...`.
- In `KEY_TABLE`:
  - `["1–5", ...]` becomes `["1–6", "workspace · run · questions for you · export · audit log · gap check"]`;
  - the `r` row becomes `["r", "re-run live (Run); run the gap check or check again (Gap check)"]`;
  - the `e` row becomes `["e", "export xlsx (Run, Export); the gap report (Gap check)"]`;
  - add `["g i p d s o a", "gap check scope: govern · identify · protect · detect · respond · recover · all core"]` after the `v p c u y x` row.

`web/src/App.tsx`: import `GapCheck` and render `{route.view === "gap" && <GapCheck {...props} scope={route.scope} outcome={route.item} />}`.

`web/src/views/Export.tsx` (decision 5): after the sentence ending `A csv comes back as csv.`, add ` If you ran a gap check, an xlsx also gets a Gap report sheet with the latest one, its scope and its date.` Append to `web/src/views/Export.test.tsx`'s describe block:

```tsx
  it("says an xlsx carries the latest gap check", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<ExportView workspace={fixtures.workspace} onGone={() => {}} runId="r1" />);
    expect(await screen.findByText(/an xlsx also gets a Gap report sheet/)).toBeInTheDocument();
  });
```

`web/src/test/mockApi.ts`: import `GapOut` and `GapRow`, and add to `fixtures`:

```ts
const gapRow = (
  csf_id: string, fn: string, category: string, tier: GapRow["tier"], label: GapRow["label"], explanation: string | null,
): GapRow => ({
  csf_id, function: fn, category, outcome: `NIST's outcome text for ${csf_id}.`, related_controls: ["CP-09"],
  source_url: "https://csrc.nist.gov/projects/cybersecurity-framework/filters#/csf/filters", tier,
  item_id: tier === "not_checked" ? null : `i-${csf_id}`, answer_id: label ? `a-${csf_id}` : null, label, explanation,
  sources: label === "covered" ? 1 : 0,
});
const gap: GapOut = {
  scope: "core", csf_version: "2.0", retrieved: "2026-10-05",
  controls_url: "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final",
  run: { ...run, id: "r9", questionnaire_id: "q9", total: 2, done: 2 },
  rows: [
    gapRow("GV.RM-02", "Govern", "Risk Management Strategy", "ask", "not_answered", null),
    gapRow("PR.DS-11", "Protect", "Data Security", "checked", "covered", "Evidenced: parts 1, 2, 3, 4."),
    gapRow("PR.DS-01", "Protect", "Data Security", "checked", "gap", "No evidence: parts 1, 2, 3."),
    gapRow("PR.DS-10", "Protect", "Data Security", "not_checked", null, null),
  ],
};
```

Append to `web/src/lib/route.test.ts`:

```ts
it("the gap view keeps its scope and outcome in the query string", () => {
  const r = readRoute("?view=gap&scope=protect&item=PR.DS-11");
  expect(r).toEqual({ view: "gap", scope: "protect", item: "PR.DS-11" });
  expect(href(r)).toBe("?view=gap&item=PR.DS-11&scope=protect");
});
```

Append inside `describe("Shell", ...)` in `web/src/components/Shell.test.tsx`:

```tsx
  it("the gap check is view 6 and opens without a run", () => {
    window.history.replaceState(null, "", "?view=workspace");
    render(<Shell mode="WORKSPACE" cursor="" hints={[]} expiresAt={null}>x</Shell>);
    const tab = screen.getByRole("link", { name: /gap check/ });
    expect(tab).toHaveAttribute("aria-keyshortcuts", "6");
    expect(tab).toHaveAttribute("href", "?view=gap");
  });
```

- [ ] **Step 2: Write the failing view tests**

`web/src/views/GapCheck.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { GAP_FOOTER, GAP_REVIEW } from "../lib/labels";
import { fixtures, mockApi } from "../test/mockApi";
import GapCheck, { coverage } from "./GapCheck";

const props = { workspace: fixtures.workspace, onGone: () => {} };
const OUTCOME = /^[A-Z]{2}\.[A-Z]{2}-\d\d /;

describe("GapCheck", () => {
  beforeEach(() => window.history.replaceState(null, "", "?view=gap"));

  it("counts the coverage line from the rows", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    expect(await screen.findByText("checked 2 · ask me 1 · not checked 1 · of 4")).toBeInTheDocument();
    expect(coverage(fixtures.gap.rows)).toBe("checked 2 · ask me 1 · not checked 1 · of 4");
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
    const gap = within(group).getByRole("button", { name: /^gap 1$/ });
    await userEvent.click(gap);
    expect(gap).toHaveAttribute("aria-pressed", "true");
    const shown = screen.getAllByRole("row", { name: OUTCOME }).map((r) => r.getAttribute("aria-label")?.slice(0, 8));
    expect(shown).toEqual(["PR.DS-01"]);
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

  it("e downloads the gap report of the run", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    const { container } = render(<GapCheck {...props} />);
    await screen.findByRole("button", { name: "Check again" });
    expect(container.querySelector("a[download]")).toHaveAttribute("href", "/api/runs/r9/export");
  });

  it("an outcome marked not applicable says so, on either tier", async () => {
    const na = { ...fixtures.gap.rows[2], label: null, not_applicable: true, explanation: "Not applicable: no such data" };
    mockApi({ "GET /api/gap/core": { ...fixtures.gap, rows: [fixtures.gap.rows[0], fixtures.gap.rows[1], na, fixtures.gap.rows[3]] } });
    render(<GapCheck {...props} />);
    const row = await screen.findByRole("row", { name: /^PR\.DS-01 / });
    expect(row).toHaveTextContent("not applicable");
    expect(row).toHaveTextContent("Not applicable: no such data");
  });

  it("check again with nothing changed says so", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap, "POST /api/gap/core/run": fixtures.gap.run });
    render(<GapCheck {...props} />);
    await screen.findByRole("button", { name: "Check again" });
    await userEvent.keyboard("r");
    expect(await screen.findByText("Nothing changed since the last check.")).toBeInTheDocument();
  });

  it("a click or enter on a row opens that outcome", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap });
    render(<GapCheck {...props} />);
    await userEvent.click(await screen.findByRole("row", { name: /^PR\.DS-11 / }));
    expect(window.location.search).toBe("?view=gap&item=PR.DS-11&scope=core");
  });
});
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd web && npx vitest run src/views/GapCheck.test.tsx src/lib/route.test.ts src/components/Shell.test.tsx`
Expected: FAIL. `./GapCheck` does not exist, and the route and Shell tests fail on the missing view.

- [ ] **Step 4: Write the view**

`web/src/views/GapCheck.tsx`:

```tsx
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, GapChip, Kbd } from "../components/ui";
import { api, messageOf, type GapLabel, type GapOut, type GapRow, type GapScope, type RunRowsOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { GAP_FOOTER, GAP_LABELS, GAP_REVIEW, SCOPES, SCOPE_KEY } from "../lib/labels";
import { go } from "../lib/route";
import { useStepLoop } from "./RunGrid";

const NOT_CHECKED = "not checked in this version"; // CSF spec 5.5
type Filter = GapLabel | "not_checked";
const FILTERS: readonly Filter[] = [...GAP_LABELS, "not_checked"];

/** The status line (CSF spec 7): counted from the rows, never typed in, so coverage is never overstated. */
export function coverage(rows: GapRow[]): string {
  const n = (tier: GapRow["tier"]) => rows.filter((r) => r.tier === tier).length;
  return `checked ${n("checked")} · ask me ${n("ask")} · not checked ${n("not_checked")} · of ${rows.length}`;
}

const filterOf = (r: GapRow): Filter | null => (r.tier === "not_checked" ? "not_checked" : r.label);
const group = (r: GapRow) => `${r.function} / ${r.category}`.toLowerCase();

type RowProps = { row: GapRow; i: number; cursor: boolean; selected: boolean; section: string | null; pending: boolean };

/** One 28px line per outcome (design.md List row), under a `# function / category` line when that changes. */
const Row = memo(function Row({ row: r, i, cursor, selected, section, pending }: RowProps) {
  const quiet = r.tier === "not_checked" || !r.label;
  const note =
    r.tier === "not_checked" ? NOT_CHECKED : (r.explanation ?? (pending ? "checking…" : r.answer_id ? "" : "not run yet"));
  const word = r.label ? <GapChip label={r.label} /> : r.not_applicable ? "not applicable" : r.tier === "not_checked" ? "not checked" : "";
  return (
    <>
      {section !== null && (
        <tr className="h-6 border-b border-rule-strong text-xs text-ink-3">
          <td colSpan={6} className="truncate px-2"># {section}</td>
        </tr>
      )}
      <tr
        data-i={i}
        tabIndex={cursor ? 0 : -1}
        aria-selected={selected}
        aria-label={`${r.csf_id} ${r.outcome}`}
        className={`h-7 cursor-pointer border-b border-rule hover:bg-sunken focus-visible:-outline-offset-2 ${selected ? "bg-sunken font-medium outline-2 -outline-offset-2 outline-ink" : ""} ${quiet ? "text-ink-3" : ""}`}
      >
        <td aria-hidden="true" className="pl-2 font-bold">{cursor ? ">" : ""}</td>
        <td className="truncate px-2">{r.csf_id}</td>
        <td className="truncate px-2">{word}</td>
        <td className="px-2 text-right tabular-nums">{r.label ? r.sources : ""}</td>
        <td className="truncate px-2">{r.outcome}</td>
        <td className={`truncate px-2 ${quiet ? "" : "text-ink-2"}`}>{note}</td>
      </tr>
    </>
  );
});

export default function GapCheck({ workspace, onGone, scope, outcome }: ViewProps & { scope?: string; outcome?: string }) {
  const current: GapScope = SCOPES.find((s) => s === scope) ?? "core";
  const [loaded, setData] = useState<GapOut | null>(null);
  const data = loaded?.scope === current ? loaded : null; // another scope's rows never show
  const [tick, setTick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Set<Filter>>(new Set());
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const download = useRef<HTMLAnchorElement>(null);
  const body = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    let alive = true; // a slow answer for an old scope or tick never lands
    api.gap(current).then(
      (d) => { if (alive) { setData(d); setError(null); } },
      (e) => { if (alive) setError(goneOn404(e, onGone)); },
    );
    return () => { alive = false; };
  }, [current, onGone, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  // The Run grid's loop drives the steps; after each one the rows are read again from GET /api/gap/{scope}.
  const run = data?.run ?? null;
  const loop = useMemo<RunRowsOut | null>(() => (run ? { run, rows: [] } : null), [run]);
  const { error: loopError, running } = useStepLoop(run?.id ?? "", loop, reload, onGone);

  const rows = data?.rows;
  const counts = useMemo(() => {
    const c = Object.fromEntries(FILTERS.map((l) => [l, 0])) as Record<Filter, number>;
    for (const r of rows ?? []) {
      const k = filterOf(r);
      if (k) c[k] += 1;
    }
    return c;
  }, [rows]);
  const visible = useMemo(
    () => (rows ?? []).filter((r) => { const k = filterOf(r); return filters.size === 0 || (k !== null && filters.has(k)); }),
    [rows, filters],
  );
  const sections = useMemo(
    () => visible.map((r, i) => (i === 0 || group(r) !== group(visible[i - 1]) ? group(r) : null)),
    [visible],
  );
  const cur = Math.max(0, Math.min(cursor, visible.length - 1));
  useEffect(() => { body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); }, [cur]);

  const toggle = (l: Filter) => setFilters((f) => { const n = new Set(f); if (n.has(l)) n.delete(l); else n.add(l); return n; });
  const openRow = (i: number) => { const r = visible[i]; if (r) go({ view: "gap", scope: current, item: r.csf_id }); };
  const rowAt = (e: MouseEvent | KeyboardEvent) => {
    const tr = (e.target as HTMLElement).closest<HTMLElement>("tr[data-i]");
    return tr ? Number(tr.dataset.i) : null;
  };
  const [note, setNote] = useState<string | null>(null);
  const start = async () => {
    if (!data || busy || running) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const out = await api.startGap(current);
      // adversary-1 M7: say so when Check again found nothing to re-open (the press still counts under `run`)
      if (data.run?.id === out.id && out.status === "done") setNote("Nothing changed since the last check.");
      reload();
    } catch (e) { setError(messageOf(e)); }
    setBusy(false);
  };
  const exportFile = () => { if (run) download.current?.click(); };
  const down = () => setCursor(Math.min(cur + 1, visible.length - 1));
  const up = () => setCursor(Math.max(cur - 1, 0));

  useKeys({
    ...Object.fromEntries(SCOPES.map((s) => [SCOPE_KEY[s], () => go({ view: "gap", scope: s })])),
    j: down,
    ArrowDown: down,
    k: up,
    ArrowUp: up,
    r: () => void start(),
    e: exportFile,
  });

  const status = running ? "Checking." : run?.status === "done" ? `Gap check done: ${run.done} of ${run.total} checked.` : "";
  return (
    <Shell
      mode="GAP"
      cursor={data ? coverage(data.rows) : ""}
      hints={[["g i p d s o a", "scope"], ["r", "run"], ["e", "export"], ["?", "all keys"]]}
      expiresAt={workspace.expires_at}
    >
      <div className="grid h-full min-h-0">
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-rule-strong px-4 py-2">
            <div className="min-w-0">
              <h1 className="text-base font-medium [overflow-wrap:anywhere]">
                workspace<span className="px-1 text-ink-3">/</span>csf 2.0<span className="px-1 text-ink-3">/</span>{current}
              </h1>
              <p className="text-xs text-ink-3">
                {GAP_REVIEW} · labels decided by code
                {run ? ` · ${run.done} of ${run.total} checked · ${running ? "checking" : run.status} · $${run.cost_usd.toFixed(4)}` : " · not run yet"}
              </p>
              <p role="status" className="sr-only">{status}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button k="r" label={run ? "Check again" : "Run gap check"} primary onClick={() => void start()} busy={busy} busyLabel="Starting…" disabled={!data || running} />
              <Button k="e" label="Export xlsx" onClick={exportFile} disabled={!run} />
              {run && <a ref={download} href={api.exportUrl(run.id)} download hidden tabIndex={-1} aria-hidden="true" />}
            </div>
          </div>
          <div role="group" aria-label="scope" className="flex flex-wrap gap-x-3 gap-y-1 border-b border-rule-strong px-4 py-1 text-xs">
            {SCOPES.map((s) => (
              <button key={s} type="button" aria-pressed={s === current} aria-keyshortcuts={SCOPE_KEY[s]} onClick={() => go({ view: "gap", scope: s })}
                className={`flex h-6 items-center gap-1 whitespace-nowrap border px-1 hover:border-rule-strong ${s === current ? "border-ink font-medium" : "border-transparent"}`}>
                <Kbd>{SCOPE_KEY[s]}</Kbd>{s === "core" ? "all core" : s}
              </button>
            ))}
          </div>
          {/* no single keys: g i p d s o a r e are taken (plan 6B note 11); Tab reaches each toggle */}
          <div role="group" aria-label="filter by label" className="flex flex-wrap gap-x-3 gap-y-1 border-b border-rule-strong bg-sunken px-4 py-1">
            {FILTERS.map((l) => (
              <button key={l} type="button" aria-pressed={filters.has(l)} onClick={() => toggle(l)}
                className={`flex h-6 items-center gap-1 whitespace-nowrap border px-1 text-xs hover:border-rule-strong hover:bg-paper ${filters.has(l) ? "border-ink bg-paper" : "border-transparent"}`}>
                {l === "not_checked" ? <span className="px-1 text-ink-3">not checked</span> : <GapChip label={l} />}{" "}
                <span className="font-bold tabular-nums">{counts[l]}</span>
              </button>
            ))}
          </div>
          <div className="px-4"><ErrorLine message={error ?? loopError} /></div>
          {note && <p role="status" className="px-4 text-xs text-ink-2">{note}</p>}
          <div className="min-h-0 flex-1 overflow-auto">
            <table aria-label="outcomes" aria-rowcount={visible.length + 1} className="w-full min-w-[56rem] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[3ch]" /><col className="w-[10ch]" /><col className="w-[19ch]" /><col className="w-[6ch]" />
                <col className="w-[40%]" /><col />
              </colgroup>
              <thead className="sticky top-0 z-[1] bg-paper text-left text-xs font-medium text-ink-2">
                <tr className="h-6 border-b border-ink">
                  <th scope="col"><span className="sr-only">cursor</span></th>
                  <th scope="col" className="px-2">id</th>
                  <th scope="col" className="px-2">label</th>
                  <th scope="col" className="px-2 text-right">src</th>
                  <th scope="col" className="px-2">nist outcome</th>
                  <th scope="col" className="px-2">explanation</th>
                </tr>
              </thead>
              <tbody
                ref={body}
                onClick={(e) => { const i = rowAt(e); if (i !== null) { setCursor(i); openRow(i); } }}
                onKeyDown={(e) => { const i = rowAt(e); if (e.key === "Enter" && i !== null) { e.preventDefault(); openRow(i); } }}
              >
                {visible.map((r, i) => (
                  <Row key={r.csf_id} row={r} i={i} cursor={i === cur} selected={r.csf_id === outcome} section={sections[i]}
                    pending={running && r.tier !== "not_checked" && !r.answer_id} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-rule-strong px-4 py-1 text-xs text-ink-3">{GAP_FOOTER}</p>
        </div>
      </div>
    </Shell>
  );
}
```

- [ ] **Step 5: Write the design.md lines**

In the keyboard map table:
- the `1`–`5` row becomes `` | `1`–`6` | workspace · run · questions for you · export · audit log · gap check | everywhere in a workspace | ``;
- add `` | `g` `i` `p` `d` `s` `o` `a` | scope: govern · identify · protect · detect · respond · recover · all core | Gap check | ``;
- add `` | `r` | run the gap check, or check again (each press counts under the per-network `run` limit, 20 an hour) | Gap check | ``;
- add `` | `e` | export the gap report (xlsx) | Gap check | ``.

Add to the change log:

```markdown
- 2026-10-06 · Gap check (Plan 6B): view 6 in the Workbench layout; scope keys g i p d s o a; gap label chips
  (covered fill, partly 1px, not met 1px bold, DISAGREE 2px uppercase, gap dashed, confirmed by you neutral-700
  fill, not answered quiet); the filter toggles are Tab-reached with no single keys (g i p d s o a r e are taken);
  the coverage line sits in the status line's cursor slot.
```

- [ ] **Step 6: Run the tests and the chain**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS, including the existing RunGrid, Shell, App and route tests.

- [ ] **Step 7: Commit**

```bash
git add web/src design.md
git commit -m "feat(web): the Gap check view, scope keys, filter counts and the coverage line" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The gap inspector

**Lane:** ui (after Task 5). **Implementer:** Opus 5.5. **Reviewer:** Opus. **Eval key:** none.

**Files:**
- Create: `web/src/views/GapDrawer.tsx`, `web/src/views/GapDrawer.test.tsx`
- Modify:
  - `web/src/views/EvidenceDrawer.tsx`: `DrawerFrame` and `DroppedList` extracted and exported, behaviour unchanged;
  - `web/src/views/Questions.tsx`: `QuestionCard` exported;
  - `web/src/views/GapCheck.tsx`: renders the drawer;
  - `web/src/views/GapCheck.test.tsx`;
  - `web/src/lib/api.ts`: `DroppedOut`;
  - `web/src/test/mockApi.ts`: `fixtures.gapDetail`.

**Interfaces:**
- Consumes:
  - from Tasks 1, 3 and 5: `GapRow`, `AnswerDetail.parts`, `PartOut` and `GapChip`; `GAP_REVIEW`;
  - existing: `Citation`, `QuestionCard`, `api.answer`, `api.questions`, `api.answerQuestion`.
- Produces:
  - `DrawerFrame({ title, titleId, root, onClose, children })` and `DroppedList({ dropped })` from `EvidenceDrawer.tsx`;
  - `GapDrawer({ row, runId, controlsUrl, onClose, onChanged })`;
  - `fixtures.gapDetail` (PR.DS-11 with two parts: part 1 covered, citing a draft line; part 2 gap).

The CSF spec 7 inspector, reusing the Plan 3 drawer:
- the label;
- NIST's verbatim outcome with its link;
- the related 800-53 controls as links;
- VART's explanation;
- per-part status (carry d): each part's chip, question and footnote refs into `sources (n)`; a draft-only quote shows `draft` in its Citation caption;
- the line listings;
- dropped evidence;
- for an Ask-me outcome, its question and the Questions-for-you answer box.

- [ ] **Step 1: Write the failing tests**

Add to `fixtures` in `web/src/test/mockApi.ts`:

```ts
const gapCite = {
  ...detail.citations[0], filename: "backup-policy.docx", status: "draft" as const, line: 2,
  quote: "Backups of data are created daily.", context: [{ n: 2, text: "Backups of data are created daily.", cited: true }],
};
const gapDetail: AnswerDetail = {
  ...detail, id: "a-PR.DS-11", item_id: "i-PR.DS-11", label: "partial", value: "Partial",
  text: "Evidenced: part 1. No evidence: part 2.",
  item: { ...detail.item, id: "i-PR.DS-11", code: "PR.DS-11", csf_id: "PR.DS-11", question: "Are backups of data created and tested?" },
  citations: [gapCite],
  parts: [
    { n: 1, question: "Are backups of data created?", label: "covered", citations: [gapCite], dropped: [], from_statement: false },
    { n: 2, question: "Are backups of data tested?", label: "gap", citations: [], dropped: [], from_statement: false },
  ],
};
```

`web/src/views/GapDrawer.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { QuestionOut } from "../lib/api";
import { fixtures, mockApi } from "../test/mockApi";
import GapDrawer from "./GapDrawer";

const [ask, checked, , unchecked] = fixtures.gap.rows;
const base = { runId: "r9", controlsUrl: fixtures.gap.controls_url, onClose: () => {}, onChanged: () => {} };

describe("GapDrawer", () => {
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
    expect(screen.getByText(/saved as a dated statement and can be cited in your questionnaires/)).toBeInTheDocument(); // adversary-1 M9
  });

  it("an outcome marked not applicable reads so in the inspector", () => {
    mockApi({});
    render(<GapDrawer {...base} row={{ ...unchecked, tier: "checked", not_applicable: true, answer_id: null }} />);
    expect(screen.getByText("not applicable")).toBeInTheDocument();
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
```

Append inside `describe("GapCheck", ...)` in `GapCheck.test.tsx`:

```tsx
  it("the outcome in the route opens its inspector and esc goes back to the list", async () => {
    mockApi({ "GET /api/gap/core": fixtures.gap, "GET /api/answers/a-PR.DS-11": fixtures.gapDetail });
    render(<GapCheck {...props} outcome="PR.DS-11" />);
    expect(await screen.findByRole("complementary")).toHaveTextContent("PR.DS-11 · gap check");
    await userEvent.keyboard("p"); // list keys are off while the inspector is open
    expect(window.location.search).toBe("?view=gap");
    await userEvent.keyboard("{Escape}");
    expect(window.location.search).toBe("?view=gap&scope=core");
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/views/GapDrawer.test.tsx src/views/GapCheck.test.tsx`
Expected: FAIL. `./GapDrawer` does not exist, and the view opens no inspector.

- [ ] **Step 3: Extract `DrawerFrame` and `DroppedList`, export `QuestionCard`**

In `web/src/lib/api.ts`, add `export type DroppedOut = S["DroppedOut"];`. In `web/src/views/Questions.tsx`, change `function QuestionCard` to `export function QuestionCard`.

In `web/src/views/EvidenceDrawer.tsx`, import `type ReactNode` and `type RefObject` from react and `type DroppedOut` from the API, and add:

```tsx
type FrameProps = { title: string; titleId: string; root: RefObject<HTMLElement | null>; onClose: () => void; children: ReactNode };

/** design.md Inspector drawer, shared by the Evidence drawer and the gap inspector: a right column, not modal;
 * under 900px a full-screen dialog that takes focus and traps Tab. Esc closes; the caller gives focus back. */
export function DrawerFrame({ title, titleId, root, onClose, children }: FrameProps) {
  const narrow = useNarrow();
  useKeys({ Escape: onClose });
  useEffect(() => { if (narrow) root.current?.querySelector<HTMLElement>("button")?.focus(); }, [narrow, root]); // the close control exists before the body loads
  const trap = (e: ReactKeyboardEvent) => {
    if (!narrow || e.key !== "Tab" || !root.current) return;
    const items = Array.from(root.current.querySelectorAll<HTMLElement>("button:not([disabled]), input, textarea, select, a[href]"));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (!root.current.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; } // the focused control went away
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  return (
    <aside
      ref={root}
      tabIndex={-1}
      aria-labelledby={titleId}
      role={narrow ? "dialog" : undefined}
      aria-modal={narrow ? true : undefined}
      onKeyDown={trap}
      className={`focus:outline-none ${narrow ? "fixed inset-0 z-10" : "border-l border-ink"} flex min-h-0 flex-col overflow-auto bg-paper transition duration-200 ease-out`}
    >
      <div data-chrome className="flex h-8 items-center justify-between bg-chrome px-3 text-xs">
        <span className="font-bold text-on-chrome">{title}</span>
        <Button k="esc" shortcut="Escape" label="close" quiet onClick={onClose} />
      </div>
      <div className="space-y-4 p-3 text-sm">{children}</div>
    </aside>
  );
}

export function DroppedList({ dropped }: { dropped: DroppedOut[] }) {
  return (
    <section>
      <h3 className="border-b border-ink text-xs font-medium text-ink-2">dropped evidence ({dropped.length})</h3>
      <ul className="divide-y divide-rule">
        {dropped.map((d, i) => (
          <li key={i} className="py-1 text-xs">
            <span className="font-bold">{d.reason.replace(/-/g, " ").toUpperCase()}</span>{" "}
            <span>{d.filename}{d.line ? `:${d.line}` : ""}</span>{" "}
            <span className="text-ink-2">{d.sentence}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

Then, in `Drawer`:
- remove `narrow`, `trap` and the narrow focus effect;
- remove `Escape: onClose` from its `useKeys` (the frame has it);
- replace the `<aside>…</aside>` and its header with `<DrawerFrame root={root} title={`${code} · evidence`} titleId={titleId} onClose={onClose}>` around the same body children (`ErrorLine` and the `a && (...)` block), with the dropped-evidence section replaced by `<DroppedList dropped={a.dropped} />`.

`useNarrow` and `Citation` stay exported from this file.

- [ ] **Step 4: Write the inspector and wire it into the view**

`web/src/views/GapDrawer.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { ErrorLine, GapChip } from "../components/ui";
import { api, messageOf, type AnswerDetail, type CitationOut, type GapRow, type QuestionOut } from "../lib/api";
import { GAP_REVIEW } from "../lib/labels";
import { Citation, DrawerFrame, DroppedList } from "./EvidenceDrawer";
import { QuestionCard } from "./Questions";

const TO_REVIEW = new Set(["partly_covered", "not_met", "documents_disagree", "gap"]); // CSF spec 2: possible gaps

type Props = { row: GapRow; runId: string | null; controlsUrl: string; onClose: () => void; onChanged: () => void };

/** Keyed by outcome and answer, so a quick switch never shows another outcome's evidence. */
export default function GapDrawer(p: Props) {
  return <Inspector key={`${p.row.csf_id}:${p.row.answer_id ?? ""}`} {...p} />;
}

const same = (x: CitationOut, c: CitationOut) =>
  x.document_id === c.document_id && x.line === c.line && x.quote === c.quote && x.stance === c.stance;

function Inspector({ row, runId, controlsUrl, onClose, onChanged }: Props) {
  const root = useRef<HTMLElement>(null);
  const [a, setA] = useState<AnswerDetail | null>(null);
  const [question, setQuestion] = useState<QuestionOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { answer_id: answerId, item_id: itemId, tier } = row;
  const titleId = `gap-${row.csf_id}`;

  useEffect(() => {
    let alive = true;
    const fail = (e: unknown) => { if (alive) setError(messageOf(e)); };
    if (answerId) api.answer(answerId).then((d) => { if (alive) setA(d); }, fail);
    if (tier === "ask" && runId && itemId) {
      api.questions(runId).then((qs) => { if (alive) setQuestion(qs.find((q) => q.item_ids.includes(itemId)) ?? null); }, fail);
    }
    return () => { alive = false; };
  }, [answerId, itemId, tier, runId]);

  const parts = a?.parts ?? [];
  const ref = (c: CitationOut) => (a?.citations.findIndex((x) => same(x, c)) ?? -1) + 1; // footnote into sources
  return (
    <DrawerFrame root={root} title={`${row.csf_id} · gap check`} titleId={titleId} onClose={onClose}>
      <ErrorLine message={error} />
      <h2 id={titleId} className="text-base font-medium [overflow-wrap:anywhere]">{row.outcome}</h2>
      <p className="text-xs text-ink-3">
        NIST's text, verbatim ·{" "}
        <a href={row.source_url} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-2">NIST CSF 2.0 reference tool</a>
      </p>
      <dl className="grid grid-cols-[11ch_minmax(0,1fr)] gap-y-1">
        <dt className="text-ink-3">label</dt>
        <dd>{row.label ? <GapChip label={row.label} /> : row.not_applicable ? "not applicable" : tier === "not_checked" ? "not checked in this version" : "not run yet"}</dd>
        <dt className="text-ink-3">function</dt><dd>{row.function}</dd>
        <dt className="text-ink-3">category</dt><dd>{row.category}</dd>
        <dt className="text-ink-3">800-53</dt>
        <dd className="flex flex-wrap gap-x-2">
          {row.related_controls.length === 0 ? "—" : row.related_controls.map((c) => (
            <a key={c} href={controlsUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2">{c}</a>
          ))}
        </dd>
      </dl>
      {row.label && TO_REVIEW.has(row.label) && <p className="font-medium">{GAP_REVIEW}</p>}
      {row.explanation && <div className="border border-rule-strong p-2 text-ink-2 [overflow-wrap:anywhere]">{row.explanation}</div>}
      {parts.length > 0 && (
        <section>
          <h3 className="border-b border-ink text-xs font-medium text-ink-2">parts ({parts.length})</h3>
          <ol className="divide-y divide-rule">
            {parts.map((p) => (
              <li key={p.n} className="flex flex-wrap items-baseline gap-2 py-1">
                <span className="font-bold">part {p.n}</span>
                <GapChip label={p.label} />
                <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{p.question}</span>
                {p.citations.map((c, i) => <sup key={i} className="font-bold">[{ref(c)}]</sup>)}
                {p.from_statement && <span className="text-xs text-ink-3">from your answer</span>}
              </li>
            ))}
          </ol>
        </section>
      )}
      {a && a.citations.length > 0 && (
        <section className="space-y-2">
          <h3 className="border-b border-ink text-xs font-medium text-ink-2">sources ({a.citations.length})</h3>
          {a.citations.map((c, i) => <Citation key={i} c={c} n={i + 1} />)}
        </section>
      )}
      {a && a.dropped.length > 0 && <DroppedList dropped={a.dropped} />}
      {tier === "ask" && (question ? (
        <>
          <ul>
            <QuestionCard q={question} focus={false} onUpdated={(q) => { setQuestion(q); onChanged(); }} onStale={onChanged} />
          </ul>
          <p className="text-xs text-ink-3">Your answer is saved as a dated statement and can be cited in your questionnaires.</p>
        </>
      ) : (
        <p className="text-ink-2">{runId ? "This question opens when the gap check is done." : "Run the gap check first, then answer this here."}</p>
      ))}
    </DrawerFrame>
  );
}
```

In `web/src/views/GapCheck.tsx`, import `GapDrawer`. Then:
- after `cur`, replace the focus effect with:

```tsx
  const open = outcome ? data?.rows.find((r) => r.csf_id === outcome) : undefined;
  const drawerOpen = open !== undefined;
  // not while the inspector is open: a full-screen one has taken focus, and the row gets it back on close
  useEffect(() => { if (!drawerOpen) body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); }, [cur, drawerOpen]);
  const close = () => { go({ view: "gap", scope: current }); body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); };
```

- pass `!open` as `useKeys`' second argument;
- replace `<div className="grid h-full min-h-0">` with:

```tsx
      <div className={`grid h-full min-h-0 ${open ? "min-[900px]:grid-cols-[minmax(0,1fr)_34rem]" : ""}`}>
```

- add, as the grid's second child, after the list column's closing `</div>`:

```tsx
        {open && data && (
          <GapDrawer row={open} runId={data.run?.id ?? null} controlsUrl={data.controls_url} onClose={close} onChanged={reload} />
        )}
```

- [ ] **Step 5: Run the tests and the chain**

Run: `cd web && npm run lint && npm test && npm run build && cd .. && python scripts/check_monochrome.py`
Expected: PASS. `EvidenceDrawer.test.tsx` passes unchanged, which shows the extraction kept the behaviour.

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): the gap inspector: NIST's text and links, per-part status, sources, Ask-me answers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The planted improvement plan joins the sample pack (data lane)

**Lane:** data, worktree `VART-wt-6b-data`, database `vart_test_6b_data`, run by the lead (it records). It starts after adversary checkpoint 1 and runs in parallel with the api and ui lanes. **Reviewer:** Opus (every key change derived, no gate touched). **Eval key:** under $0.25 for the dev re-record (most items may re-rank, adversary-1 M10); $0.04 more only if gap-dev drifts. **Stop point:** Step 6.

**Files:**
- Create: `data/dev/src/sip.md` (the planted plan's source, for `datakit.render`)
- Create (rendered): `data/dev/docs/security-improvement-plan.md`
- Delete: `data/dev/gap/docs/security-improvement-plan.md` (and the empty `data/dev/gap/docs/`)
- Modify:
  - `data/dev/facts.yaml`: the `sip` document, the five `sip-*` statements, the controls they name that the dev sheet lacks, and traps G1-G4, each appended at the end of its list;
  - `data/dev/gap/facts.yaml`: the same entries removed; its header comment says the planted plan now lives in the dev pack;
  - `app/api/documents.py`: `SAMPLE_ORDER` gains `security-improvement-plan.md` at the end; its "rules classify all 22" comment says 23;
  - `tests/test_api_documents.py` (22 → 23 at lines 91 and 117);
  - `tests/test_eval_run.py:310` (`("sample", 22)` → `("sample", 23)`);
  - `tests/datakit/test_gap.py`: where a test looks for the `sip` entries in the gap sheet, it looks in the dev sheet, with the same assertions;
  - `data/NOTICE.md`, only if it lists the dev documents.
- Re-derived, never edited by hand:
  - `data/dev/key/vsq-a.yaml` and `data/dev/key/mvsp-b.yaml` (`python -m datakit.derive_key dev`);
  - `data/dev/key/csf-core.yaml` (`python -m datakit.gap dev`), expected byte-identical.
- Re-recorded: `evals/recorded/dev.jsonl` (appended), `evals/results/latest.json` and `evals/results/latest.md`. `evals/recorded/gap-dev.jsonl` and `evals/results/gap-dev.*` change only under Step 7's rule.

**Interfaces:**
- Consumes: `datakit.render`, `datakit.derive_key`, `datakit.gap`, `datakit.validate` (unchanged), and `datakit.gap.doc_path`, which reads a document from `data/dev/docs` once its id is not in the gap sheet.
- Produces:
  - the sample pack with 23 documents;
  - `/api/documents/sample` loads `security-improvement-plan.md` (rules classify it: kind `plan`, final, effective 2026-07-01; no model call);
  - re-derived questionnaire keys;
  - a re-recorded dev eval whose gating gates all pass.

The planted plan states two non-compliances (threat intelligence not yet received, not yet used in analysis) and one disagreement (G1: alerts not yet routed to on-call, against the logging policy). In the sample pack it gives the live demo's Not met (stated) on ID.RA-02 and DE.AE-07. The questionnaires can see it too:
- G1 becomes a planted conflict for any item whose control is `alerting`;
- the planned-only traps G2-G4 enter the dev pack.

That is why the dev keys are re-derived and the dev gates re-checked.

- [ ] **Step 1: Update the counts the tests pin**

In `tests/test_api_documents.py`, change `len(first.json()) == 22` to `== 23`, and `n == 22 and len(set(names)) == 22` to `n == 23 and len(set(names)) == 23`. In `tests/test_eval_run.py:310`, change `("sample", 22)` to `("sample", 23)`.

Run: `pytest tests/test_api_documents.py tests/test_eval_run.py -v`
Expected: FAIL. The pack still has 22 documents, and `SAMPLE_ORDER` does not match a 23-document fact sheet yet.

- [ ] **Step 2: Move the document and its facts**

- `git mv data/dev/gap/docs/security-improvement-plan.md data/dev/src/sip.md`. The source is Markdown; `datakit.render` writes `data/dev/docs/<filename>` from `data/dev/src/<id>.md`.
- Cut from `data/dev/gap/facts.yaml` and append, unchanged, to the end of the matching lists in `data/dev/facts.yaml`:
  - the `documents` entry `sip`;
  - the statements `sip-threat-intel-sources`, `sip-threat-intel-analysis`, `sip-alerting`, `sip-incident-analysis` and `sip-incident-containment`;
  - every gap-sheet control that a moved statement names and the dev sheet lacks (`threat-intel-sources`, `threat-intel-analysis`, `incident-analysis` and `incident-containment`; `alerting` is already a dev control);
  - traps G1-G4 (each names a `sip-*` statement).
- Appending keeps the merged sheet `datakit.gap` builds (dev first, then gap) in the same order as before, so the gap key and gap-dev do not move.
- Delete the emptied `documents:` and `traps:` keys from `data/dev/gap/facts.yaml`: a bare key loads as `None`, which `GapFacts` refuses, and its tuple fields default to `()` (adversary-1 M10).
- In `data/dev/gap/facts.yaml`'s header comment, add the line: `The planted improvement plan (sip) and its traps G1-G4 moved to data/dev/facts.yaml in Plan 6B, so the sample pack shows a stated non-compliance.`
- In `app/api/documents.py`, append `"security-improvement-plan.md"` to `SAMPLE_ORDER`, and change the comment's 22 to 23.

Then run:

```bash
python -m datakit.render dev
cmp data/dev/docs/security-improvement-plan.md <(git show HEAD:data/dev/gap/docs/security-improvement-plan.md)
```

Expected: no output from `cmp`, so the rendered file is byte-identical to the one gap-dev was recorded on. If `cmp` reports a difference, keep the rendered file; Step 7 then re-records gap-dev.

- [ ] **Step 3: Validate and re-derive the keys**

Run: `python -m datakit.validate all`
Expected: `datakit.validate all: 0 problems`.

A "conflict without a planted trap" or a statement not found means the move missed an entry. Fix the move, never the key. If a problem can only be fixed by changing a fact, stop and take it to Tarun.

Run: `python -m datakit.derive_key dev && python -m datakit.gap dev && git diff --exit-code data/dev/key/csf-core.yaml && git diff --stat data/dev/key`
Expected:
- `csf-core.yaml` is unchanged;
- any change in `vsq-a.yaml` or `mvsp-b.yaml` is on an item whose control a `sip-*` statement names (for example `alerting`). Read the diff and check that each changed item traces to one.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_api_documents.py tests/test_eval_run.py tests/datakit -v`
Expected: PASS. That includes `test_the_sample_pack_loads_once_in_fact_sheet_order`, and the sample load's rules classify the new file with no model call. If the rules classify it differently from its fact-sheet entry (kind `plan`, final, 2026-07-01), stop: `app/classify.py` is not this plan's to change.

- [ ] **Step 5 (lead): Re-record the dev eval**

```bash
(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack dev --mode record)
```

Expected: under $0.25. Only items whose prompts changed are paid, and the rest replay. But a 23rd document shifts the IDF for every query, so most items may re-rank and re-record (adversary-1 M10). The command writes `evals/results/latest.{json,md}`.

- [ ] **Step 6 (lead): Re-check every dev gate — the stop point**

Run:

```bash
python -m evals.run --pack dev && cp evals/results/latest.json "$TMPDIR/first.json" \
  && python -m evals.run --pack dev && cmp evals/results/latest.json "$TMPDIR/first.json"
```

Expected: exit 0 both times, and the two replays write identical results (preflight B1 as ruled). The re-recorded results differ from `HEAD` by design, so do not compare against it.

Read `evals/results/latest.md` and check every gating gate in `evals/score.py`'s dev table against its committed value:
- `label_accuracy` ≥ 0.90: 82 of 89 today; at least 81 of 89 passes, if the item count stays 89;
- recall@8 ≥ 0.95;
- judge faithfulness ≥ 0.95;
- the planted-conflict gate, which now counts G1 as a sixth planted trap;
- the date-rule gate, and every other gate at its spec value.

**If any gating gate fails, stop here.** Do not merge the lane, do not tune a prompt, a phrasing or the key, and do not lower a gate. Send Tarun the gate, its value, the items it missed with their causes, and the cost so far. List the misses on items no `sip-*` statement names separately, as ranking drift from the new document (adversary-1 M10). He decides whether the demo keeps the document.

- [ ] **Step 7 (lead): gap-dev must not move**

Run: `python -m evals.run --pack gap-dev && git diff --exit-code evals/results/gap-dev.json evals/results/gap-dev.md`
Expected: exit 0 with no diff: gap-dev already loaded this document from the same bytes.

If there is a diff (the render changed the file, or the merged order moved):
- record gap-dev once: `(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack gap-dev --mode record)`, about $0.04;
- re-check its gating gates as in Step 6, with the same stop rule; `label_accuracy` stays reported, not gating (Tarun, 2026-10-06).

- [ ] **Step 8: Run the chains and commit**

Run: the backend chain, then `python -m datakit.validate all`.
Expected: PASS.

```bash
git add data/dev app/api/documents.py tests/test_api_documents.py tests/test_eval_run.py tests/datakit/test_gap.py evals/recorded evals/results
git commit -m "data(dev): the planted improvement plan joins the sample pack; keys re-derived, dev eval re-recorded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Add `data/NOTICE.md` if Step 2 changed it.)

---

### Task 7b: Speed-up B — the precomputed sample run

**Runs on:** `plan6b`, after the three lanes merge. It touches files from both the api lane (`app/api/runs.py`, `app/api/gap.py`) and the ui lane (`RunGrid.tsx`), and it needs Task 7's 23-document pack. **Implementer:** Opus 5.5 (Steps 2-5, 7). **Lead:** Step 1 (the merges) and Step 6 (the snapshot, live). **Reviewer:** Opus (invariants, staleness, contract additions). **Eval key:** about $0.08 (64 questionnaire items, about $0.04, plus a core gap run, about $0.04).

**Decision (Tarun, 2026-10-06; this plan's decision 13).** "Try with a sample company" copies a precomputed run instead of calling a model, so it is instant and spends nothing.
- The precomputed path covers both:
  - the sample questionnaire (`vsq-a.xlsx`) over the sample pack;
  - the **core** gap check over the sample pack. Covering it is cheap (the same script, about $0.04 more), and it makes the demo's gap view instant too. A function scope runs live.
- `data/dev/sample-run.json` is the snapshot:
  - the real engine wrote it, once, through the real endpoints (`scripts/sample_snapshot.py`, run by the lead with the eval key);
  - nobody edits it by hand;
  - it stores a digest of everything that could change an answer: the sample documents, the questionnaire, the prompt versions, the step models and the core CSF data.
- When the snapshot is stale, it is never used: the run goes live. A test fails in CI until the lead runs the script again.

**Files:**
- Create: `app/sample_run.py`, `scripts/sample_snapshot.py`, `tests/test_sample_run.py`
- Create (by the script, Step 6): `data/dev/sample-run.json`
- Modify:
  - `app/api/runs.py`: the `live` query parameter; `RunOut.precomputed`;
  - `app/api/gap.py`: `start_gap` copies the core snapshot;
  - `app/api/schemas.py`: `RunOut.precomputed: bool = False`;
  - `.vercelignore`: ship the snapshot;
  - `docs/CONTRACTS.md`: change-log lines;
  - `openapi.json`, `web/src/lib/api-types.ts`: regenerated;
  - `web/src/lib/api.ts`: `createRun(id, live = false)`;
  - `web/src/views/RunGrid.tsx`: Re-run live passes `live`, and the meta line names a precomputed run;
  - `web/src/views/RunGrid.test.tsx`.

**Interfaces:**
- Consumes:
  - `SAMPLE_DIR` and `SAMPLE_ORDER` (`app/api/documents.py`, 23 documents after Task 7);
  - `app.questionnaires.SAMPLE_DIR`;
  - the prompt versions in `app/stance.py`, `app/draft.py` and `app/classify.py`;
  - `csf.current_mapping`;
  - `runs.create_run`;
  - the stored part shape (Task 2).
- Produces:
  - `sample_run.SNAPSHOT: Path`, `QUESTIONNAIRE = "vsq-a.xlsx"`, `STEPS = ("stance", "draft", "classify", "recheck")`, `ANSWER_FIELDS` (the 11 `answers` columns `_raw` writes);
  - `sample_run.digest(models: Mapping[str, str]) -> str`;
  - `sample_run.snapshot() -> dict[str, Any] | None` (cached);
  - `sample_run.swap(values: Any, chunk: Callable[[str], str], doc: Callable[[str], str]) -> Any`: rewrites every `chunk_id`, `document_id` and `chunk_ids` in a nested value;
  - `sample_run.copy_questionnaire_run(session, workspace_id, questionnaire_id, models) -> Run | None`;
  - `sample_run.copy_gap_run(session, workspace_id, q: Questionnaire, models) -> Run | None`;
  - `POST /api/questionnaires/{id}/runs?live=true`: optional, default false;
  - `RunOut.precomputed: bool`.

**Invariants the copy keeps:**
1. Labels and citations are the engine's, copied as they are, so `ck_answers_cited` holds and is enforced by the database.
2. Every chunk and document id is mapped to the visitor's own copies of the sample documents, by file name and chunk start line (chunking the same bytes gives the same chunks). A citation re-reads as `found_in_source`.
3. The run is `done`, costs $0.0000, carries `models["snapshot"] = <digest>`, and reads as precomputed in the UI.
4. The copy applies only when all of these hold:
   - the workspace holds exactly the sample pack, with no metadata override (`metadata_source == "rule"`), no upload and no statement;
   - the questionnaire is the sample `vsq-a.xlsx` with the snapshot's items, or the core gap questionnaire under the current CSF data;
   - the digest matches.

   Anything else runs live.
5. Re-run live (`r` in the run grid) still runs the engine. Check again on a copied gap run compares evidence as usual; with only the sample pack, nothing changed and it stays done.
6. Questions for you, the re-check and re-decide work on a copied run: they read `answers.stances`, `chunk_ids` and `run_items.parts`, which are the visitor's own ids.
7. The `run` cap, the demo-full 503 and the cookie flow are unchanged: the endpoint counts and checks before it copies.

- [ ] **Step 1 (lead): Merge the lanes**

On `plan6b`, merge the lanes with `git merge --no-ff`, in this order (each merge commit gets the trailer paragraph):
1. `plan6b-data`: first re-run its gate, `python -m evals.run --pack dev` on the data branch, which must exit 0 (preflight B1 as ruled);
2. `plan6b-api`;
3. `plan6b-ui`.

Then run `python scripts/export_openapi.py && (cd web && npm run gen:api) && git diff --exit-code openapi.json web/src/lib/api-types.ts`, the backend chain, the frontend chain, and `python -m evals.run --pack dev && python -m evals.run --pack gap-dev`.
Expected: PASS. Every merge is clean, because the lanes touch disjoint files.

- [ ] **Step 2: Write the failing tests**

`tests/test_sample_run.py`:

```python
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import sample_run
from app.api.deps import get_llm
from app.db.models import LlmUsage
from app.main import app
from app.settings import get_settings
from tests.apiclient import visitor
from tests.fakes import ByStepLLM

ROOT = Path(__file__).resolve().parent.parent
REGENERATE = "stale sample snapshot: the lead runs scripts/sample_snapshot.py with the eval key (Plan 6B Task 7b)"


def _sample(client: TestClient) -> dict:  # type: ignore[type-arg]
    assert client.post("/api/documents/sample").status_code == 201
    q = client.post("/api/questionnaires/sample/vsq-a").json()
    res = client.post(f"/api/questionnaires/{q['id']}/runs")
    assert res.status_code == 201
    return {"q": q, "run": res.json()}


def test_the_sample_snapshot_is_current() -> None:
    snap = sample_run.snapshot()
    assert snap is not None, REGENERATE
    assert snap["digest"] == sample_run.digest(get_settings().models()), REGENERATE
    assert len(snap["questionnaire"]["items"]) == 64 and len(snap["gap"]["items"]) == 36


def test_the_digest_moves_with_every_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    models = dict(get_settings().models())
    base = sample_run.digest(models)
    assert sample_run.digest({**models, "stance": "other/model"}) != base
    sample_run.sample_digest.cache_clear()
    monkeypatch.setattr(sample_run, "STANCE_PROMPT", "stance@p999")
    assert sample_run.digest(models) != base
    monkeypatch.undo()
    sample_run.sample_digest.cache_clear()
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in sample_run.SAMPLE_ORDER:
        (docs / name).write_bytes((sample_run.DOCS / name).read_bytes())
    (docs / sample_run.SAMPLE_ORDER[0]).write_bytes(b"changed")
    monkeypatch.setattr(sample_run, "DOCS", docs)
    assert sample_run.digest(models) != base
    sample_run.sample_digest.cache_clear()


def test_try_with_a_sample_company_copies_the_snapshot_with_no_model_call(db: Engine) -> None:
    client, ws_id = visitor(db)
    run = _sample(client)["run"]
    assert (run["status"], run["total"], run["done"], run["cost_usd"], run["precomputed"]) == ("done", 64, 64, 0.0, True)
    rows = client.get(f"/api/runs/{run['id']}/answers").json()["rows"]
    own = {d["id"] for d in client.get("/api/documents").json()}
    cited = [r["answer"] for r in rows if r["answer"]["label"] in ("verified", "partial")]
    assert cited
    for a in cited:
        detail = client.get(f"/api/answers/{a['id']}").json()
        assert detail["citations"]  # ck_answers_cited, and the drawer has something to show
        for c in detail["citations"]:
            assert c["document_id"] in own and c["found_in_source"], c  # the visitor's own copies
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(LlmUsage).where(LlmUsage.workspace_id == ws_id)) == 0


def test_re_run_live_runs_the_engine(db: Engine) -> None:
    client, _ = visitor(db)
    q = _sample(client)["q"]
    live = client.post(f"/api/questionnaires/{q['id']}/runs", params={"live": "true"}).json()
    assert (live["status"], live["precomputed"], live["done"]) == ("running", False, 0)


def test_an_override_or_an_upload_falls_back_to_a_live_run(db: Engine) -> None:
    client, _ = visitor(db)
    q = _sample(client)["q"]
    doc = client.get("/api/documents").json()[0]
    assert client.patch(f"/api/documents/{doc['id']}", json={"status": "draft"}).status_code == 200
    after = client.post(f"/api/questionnaires/{q['id']}/runs").json()
    assert (after["status"], after["precomputed"]) == ("running", False)


def test_a_stale_snapshot_is_never_copied(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    real = sample_run.snapshot()
    assert real is not None
    monkeypatch.setattr(sample_run, "snapshot", lambda: {**real, "digest": "0" * 16})
    client, _ = visitor(db)
    assert _sample(client)["run"]["status"] == "running"


def test_questions_rechecks_and_redecide_work_on_a_copied_run(db: Engine) -> None:
    client, _ = visitor(db)
    run = _sample(client)["run"]
    questions = client.get(f"/api/runs/{run['id']}/questions").json()
    assert questions  # the copied run has open items, planned as for any done run
    reply = json.dumps({"passages": [{"passage": 1, "stance": "irrelevant", "quote": "", "note": "x"}]})
    app.dependency_overrides[get_llm] = lambda: ByStepLLM({"recheck": reply})
    try:
        res = client.post(
            f"/api/questions/{questions[0]['id']}/answer",
            json={"text": "Yes. The security team reviews this every quarter and keeps a record."},
        )
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert res.status_code == 200 and res.json()["question"]["status"] in ("answered", "follow_up")
    doc = client.get("/api/documents").json()[0]
    assert client.patch(f"/api/documents/{doc['id']}", json={"evidence_allowed": False}).status_code == 200


def test_the_core_gap_check_is_copied_too(db: Engine) -> None:
    client, _ = visitor(db)
    _sample(client)
    run = client.post("/api/gap/core/run").json()
    assert (run["status"], run["done"], run["cost_usd"], run["precomputed"]) == ("done", 36, 0.0, True)
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    assert all(r["label"] for r in rows.values() if r["tier"] == "checked")
    detail = client.get(f"/api/answers/{rows['PR.DS-11']['answer_id']}").json()
    assert len(detail["parts"]) == 4
    assert all(c["found_in_source"] for p in detail["parts"] for c in p["citations"])
    again = client.post("/api/gap/core/run").json()  # Check again: only the sample pack, nothing changed
    assert (again["id"], again["status"]) == (run["id"], "done")
    assert client.post("/api/gap/protect/run").json()["status"] == "running"  # a function scope runs live


def test_the_snapshot_ships_with_the_function() -> None:
    lines = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
    assert "!/data/dev/sample-run.json" in lines
```

Append to `web/src/views/RunGrid.test.tsx`'s describe block:

```tsx
  it("re-run live asks for a live run, and a copied run says it is precomputed", async () => {
    const calls: string[] = [];
    mockApi({
      "GET /api/runs/r1/answers": { run: { ...fixtures.run, precomputed: true, cost_usd: 0 }, rows: fixtures.rows },
      "GET /api/questionnaires": [],
      "POST /api/questionnaires/q1/runs": (_init: RequestInit | undefined, url: URL) => {
        calls.push(url.search);
        return { ...fixtures.run, id: "r2", status: "running", done: 0, precomputed: false };
      },
    });
    render(<RunGrid workspace={fixtures.workspace} onGone={() => {}} runId="r1" />);
    expect(await screen.findByText(/precomputed sample answers/)).toBeInTheDocument();
    await userEvent.keyboard("r");
    await waitFor(() => expect(calls).toEqual(["?live=true"]));
  });
```

(`render`, `screen`, `waitFor`, `userEvent`, `mockApi` and `fixtures` are already imported in that file.)

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/test_sample_run.py -v && (cd web && npx vitest run src/views/RunGrid.test.tsx)`
Expected: FAIL. `app.sample_run` does not exist, `RunOut` has no `precomputed`, and Re-run live sends no `live`.

- [ ] **Step 4: Write `app/sample_run.py`**

```python
"""The precomputed sample run (Plan 6B Task 7b): "Try with a sample company" copies the sample questionnaire's
answers, and the core gap check's, from data/dev/sample-run.json instead of calling a model. The file is written
by scripts/sample_snapshot.py (the lead, with the eval key), never by hand. It stores a digest of everything that
could change an answer: the sample documents, the questionnaire, the prompt versions, the step models and the
core CSF data. A stale or missing file is never used: the run goes live."""

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import csf
from app.api.documents import SAMPLE_DIR as DOCS
from app.api.documents import SAMPLE_ORDER
from app.classify import PROMPT_VERSION as CLASSIFY_PROMPT
from app.db.models import Answer, Chunk, Document, Item, Questionnaire, Run, RunItem
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.questionnaires import SAMPLE_DIR as QUESTIONNAIRES
from app.services import audit_log
from app.stance import PROMPT_VERSION as STANCE_PROMPT

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "dev" / "sample-run.json"
QUESTIONNAIRE = "vsq-a.xlsx"
STEPS = ("stance", "draft", "classify", "recheck")
ANSWER_FIELDS = (
    "label", "value", "text", "citations", "dropped", "conflict", "scope_note", "confidence", "stances",
    "chunk_ids", "retrieval_dropped",
)


@cache
def sample_digest(models_key: tuple[tuple[str, str], ...]) -> str:
    h = hashlib.sha256()
    for name in SAMPLE_ORDER:
        h.update(name.encode() + b"\0" + (DOCS / name).read_bytes())
    h.update((QUESTIONNAIRES / QUESTIONNAIRE).read_bytes())
    meta = {
        "prompts": [STANCE_PROMPT, DRAFT_PROMPT, CLASSIFY_PROMPT],
        "models": dict(models_key),
        "csf": csf.current_mapping("core"),
    }
    h.update(json.dumps(meta, sort_keys=True).encode())
    return h.hexdigest()[:16]


def digest(models: Mapping[str, str]) -> str:
    return sample_digest(tuple((k, models[k]) for k in STEPS))


@cache
def snapshot() -> dict[str, Any] | None:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else None


def swap(values: Any, chunk: Callable[[str], str], doc: Callable[[str], str]) -> Any:
    """Every chunk id, document id and chunk id list in a nested answer value, rewritten. The snapshot holds
    "<file name>#<line>" and file names; a workspace holds its own ids."""
    if isinstance(values, list):
        return [swap(v, chunk, doc) for v in values]
    if not isinstance(values, dict):
        return values
    out = {k: swap(v, chunk, doc) for k, v in values.items()}
    if isinstance(out.get("chunk_id"), str):
        out["chunk_id"] = chunk(out["chunk_id"])
    if isinstance(out.get("document_id"), str):
        out["document_id"] = doc(out["document_id"])
    if isinstance(out.get("chunk_ids"), list):
        out["chunk_ids"] = [chunk(c) for c in out["chunk_ids"]]
    return out


def _current(models: Mapping[str, str]) -> dict[str, Any] | None:
    snap = snapshot()
    return snap if snap is not None and snap["digest"] == digest(models) else None


def _sample_pack_only(session: Session, workspace_id: uuid.UUID) -> bool:
    """The workspace holds the sample pack and nothing else, with no metadata changed: only then do the
    snapshot's answers describe it (an upload, an answer to a question or an override changes what the engine
    would say)."""
    docs = session.execute(
        select(Document.filename, Document.source, Document.metadata_source).where(
            Document.workspace_id == workspace_id
        )
    ).all()
    return sorted(d.filename for d in docs) == sorted(SAMPLE_ORDER) and all(
        d.source == "sample" and d.metadata_source == "rule" for d in docs
    )


def _copy(
    session: Session,
    workspace_id: uuid.UUID,
    q: Questionnaire,
    pairs: list[tuple[Item, dict[str, Any]]],
    snap: dict[str, Any],
) -> Run | None:
    rows = session.execute(
        select(Chunk.id, Chunk.line_start, Document.id, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == workspace_id)
    ).all()
    chunks = {f"{name}#{line}": str(cid) for cid, line, _, name in rows}
    docs = {name: str(did) for _, _, did, name in rows}
    try:
        local = [
            (
                item,
                swap(e["values"], chunks.__getitem__, docs.__getitem__),
                swap(e.get("parts", {}), chunks.__getitem__, docs.__getitem__),
            )
            for item, e in pairs
        ]
    except KeyError:  # a chunk the snapshot cites is not in this workspace: never copy a dangling citation
        return None
    run = Run(
        workspace_id=workspace_id,
        questionnaire_id=q.id,
        status="done",
        finished_at=datetime.now(UTC),
        prompt_versions=snap["prompt_versions"],
        models={**snap["models"], "snapshot": snap["digest"]},
    )
    session.add(run)
    session.flush()
    for item, values, parts in local:
        session.add(RunItem(run_id=run.id, item_id=item.id, state="done", parts=parts))
        session.add(Answer(workspace_id=workspace_id, run_id=run.id, item_id=item.id, **values))
    audit_log.record(
        session, workspace_id, "run.create", ref=str(run.id), detail={"items": len(local), "precomputed": True}
    )
    session.commit()
    return run


def copy_questionnaire_run(
    session: Session, workspace_id: uuid.UUID, questionnaire_id: uuid.UUID, models: Mapping[str, str]
) -> Run | None:
    """The sample questionnaire's run, copied (Task 7b); None when anything differs from the snapshot's world."""
    snap = _current(models)
    q = session.scalar(
        select(Questionnaire).where(Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == workspace_id)
    )
    if snap is None or q is None or q.source != "sample" or q.filename != QUESTIONNAIRE:
        return None
    if not _sample_pack_only(session, workspace_id):
        return None
    items = list(session.scalars(select(Item).where(Item.questionnaire_id == q.id).order_by(Item.position)))
    want = snap["questionnaire"]["items"]
    if [(i.position, i.question) for i in items] != [(e["position"], e["question"]) for e in want]:
        return None
    return _copy(session, workspace_id, q, list(zip(items, want, strict=True)), snap)


def copy_gap_run(
    session: Session, workspace_id: uuid.UUID, q: Questionnaire, models: Mapping[str, str]
) -> Run | None:
    """The core gap check's run, copied (Task 7b); None for another scope or anything that differs."""
    snap = _current(models)
    if snap is None or (q.mapping or {}).get("scope") != "core" or not _sample_pack_only(session, workspace_id):
        return None
    items = {i.csf_id: i for i in session.scalars(select(Item).where(Item.questionnaire_id == q.id))}
    want = snap["gap"]["items"]
    if sorted(items) != sorted(e["csf_id"] for e in want):
        return None
    return _copy(session, workspace_id, q, [(items[e["csf_id"]], e) for e in want], snap)
```

- [ ] **Step 5: Wire it into the endpoints, the schema and the UI**

`app/api/schemas.py`, in `RunOut`, after `finished_at`:

```python
    precomputed: bool = False  # Plan 6B Task 7b: copied from the sample snapshot, no model called
```

`app/api/runs.py`: in `run_out`, pass `precomputed="snapshot" in run.models`. In `create_run`, add the parameter `live: bool = False` and copy first:

```python
def create_run(
    questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request, live: bool = False
) -> RunOut:
    """A new run over every item, all pending. On the sample questionnaire over the untouched sample pack, the
    precomputed sample run is copied instead (done, $0, no model call) unless `live=true` (Re-run live). 422
    when the questionnaire has no items yet; 429 per network (`run`, 20 an hour); 503 when the demo is full."""
    ws_id = ws.id
    limit(request, session, "run")
    ensure_capacity(session)
    models = get_settings().models()
    if not live and (copied := copy_questionnaire_run(session, ws_id, questionnaire_id, models)) is not None:
        return run_out(session, copied)
    return run_out(session, start_run(session, ws_id, questionnaire_id, models))
```

(import `copy_questionnaire_run` from `app.sample_run`.)

`app/api/gap.py`, `start_gap`: import `copy_gap_run` from `app.sample_run`, and replace the `if run is None:` creation with:

```python
    if run is None:
        models = get_settings().models()
        run = copy_gap_run(session, ws_id, q, models) or create_run(session, ws_id, q.id, models)
```

`.vercelignore`: after `!/data/dev/docs` add `!/data/dev/sample-run.json`.

`web/src/lib/api.ts`: `createRun: (questionnaireId: string, live = false) => send<RunOut>(`/api/questionnaires/${enc(questionnaireId)}/runs${live ? "?live=true" : ""}`, "POST"),`

`web/src/views/RunGrid.tsx`:
- in `rerun`, call `api.createRun(data.run.questionnaire_id, true)`;
- in the meta line, insert ` · precomputed sample answers` after the status when `data.run.precomputed`.

Then:
- regenerate `openapi.json` and the types (the operation's path set does not change, so `tests/test_openapi.py` and `tests/test_api_errors.py` need nothing new);
- add to `docs/CONTRACTS.md`'s change log:

```markdown
- 2026-10-06: Plan 6B Task 7b (an added optional query parameter and an optional field): `POST
  /api/questionnaires/{id}/runs?live=` (default false) copies the precomputed sample run when the questionnaire
  is the sample `vsq-a.xlsx` over the untouched sample pack and `data/dev/sample-run.json` is current, and
  `POST /api/gap/core/run` does the same for the core gap check. The copy is done at $0 with no model call, and
  `RunOut.precomputed` is true for it. `live=true` (Re-run live) always runs the engine. Counted under `run` as
  before.
```

Run: `pytest tests/test_sample_run.py -k "digest or vercelignore or stale or re_run or override" -v && (cd web && npx vitest run src/views/RunGrid.test.tsx)`
Expected: these pass. The tests that copy the snapshot, and `test_the_sample_snapshot_is_current`, still fail: no snapshot exists yet.

- [ ] **Step 6 (lead): Generate the snapshot live and measure the run times**

`scripts/sample_snapshot.py`:

```python
"""Write data/dev/sample-run.json (Plan 6B Task 7b): the sample questionnaire (vsq-a) and the core gap check,
run once by the real engine over the sample pack through the real endpoints, so "Try with a sample company"
copies them with no model call. The lead runs it with the eval key against a test database; nobody edits the
file by hand. It prints the two runs' wall-clock (Task 2b's measurement).

  export DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_plan6b
  (set -a; . ~/.config/vart/eval.env; set +a; \\
   OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" LLM_MODE=live python scripts/sample_snapshot.py)
"""

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import sample_run  # noqa: E402
from app.db.models import Answer, Chunk, Document, Item, Run, RunItem  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.runs import FAILED_TEXT  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _finish(client: TestClient, run_id: str) -> float:
    start = time.monotonic()
    while client.get(f"/api/runs/{run_id}").json()["status"] == "running":
        res = client.post(f"/api/runs/{run_id}/step")
        if res.status_code != 200:
            raise SystemExit(f"step failed: {res.status_code} {res.text}")
    return time.monotonic() - start


def _entries(s: Session, run_id: uuid.UUID) -> list[dict]:  # type: ignore[type-arg]
    run = s.get_one(Run, run_id)
    found = s.execute(
        select(Chunk.id, Chunk.line_start, Document.id, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == run.workspace_id)
    ).all()
    chunk = {str(cid): f"{name}#{line}" for cid, line, _, name in found}
    doc = {str(did): name for _, _, did, name in found}
    rows = s.execute(
        select(Item, Answer, RunItem.parts)
        .join(Answer, (Answer.item_id == Item.id) & (Answer.run_id == run_id))
        .join(RunItem, (RunItem.item_id == Item.id) & (RunItem.run_id == run_id))
        .order_by(Item.position)
    ).tuples()
    out = []
    for item, a, parts in rows:
        if a.text == FAILED_TEXT or a.statement_id is not None:
            raise SystemExit(f"{item.code}: not a clean engine answer; run the script again")
        e = {
            "position": item.position,
            "question": item.question,
            "csf_id": item.csf_id,
            "values": sample_run.swap({k: getattr(a, k) for k in sample_run.ANSWER_FIELDS}, chunk.__getitem__, doc.__getitem__),
        }
        if parts:
            e["parts"] = sample_run.swap(parts, chunk.__getitem__, doc.__getitem__)
        out.append(e)
    return out


def main() -> None:
    models = get_settings().models()
    sample_run.snapshot = lambda: None  # never copy the old file while making the new one
    client = TestClient(app)
    client.get("/api/workspace")
    client.post("/api/documents/sample")
    q = client.post("/api/questionnaires/sample/vsq-a").json()
    run = client.post(f"/api/questionnaires/{q['id']}/runs", params={"live": "true"}).json()
    took_q = _finish(client, run["id"])
    gap = client.post("/api/gap/core/run").json()
    took_g = _finish(client, gap["id"])
    with Session(get_engine()) as s:
        qrun, grun = s.get_one(Run, uuid.UUID(run["id"])), s.get_one(Run, uuid.UUID(gap["id"]))
        snap = {
            "digest": sample_run.digest(models),
            "models": {k: models[k] for k in sample_run.STEPS},
            "prompt_versions": qrun.prompt_versions,
            "cost_usd": float(qrun.cost_usd + grun.cost_usd),
            "questionnaire": {"filename": sample_run.QUESTIONNAIRE, "items": _entries(s, qrun.id)},
            "gap": {"scope": "core", "items": _entries(s, grun.id)},
        }
    sample_run.SNAPSHOT.write_text(json.dumps(snap, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    client.post("/api/workspace/reset")
    print(f"64-item run {took_q:.0f} s, core gap run {took_g:.0f} s, ${snap['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
```

Make sure no other process is using the eval key's hour for this workspace. Then run the command in the docstring.

Expected:
- about $0.08;
- the printed times are about 180 s for the 64-item run and about 240 s for the core gap run (Task 2b's targets);
- the file is under 1 MB.

Record the two times and the cost in Task 9's PROGRESS entry. If a time is more than double its target, report it to Tarun with the per-step timings. Do not change `STEP_ITEMS` or `STEP_PARTS` without his OK.

Then:
- run `gitleaks dir --redact --no-banner data/dev/sample-run.json`. Expected: no leaks. The sample pack is synthetic; a planted fake secret in a quoted line would show here.
- run `pytest tests/test_sample_run.py -v`. Expected: PASS.

- [ ] **Step 7: Run every chain and commit**

Run: the backend chain, the frontend chain, `python scripts/check_monochrome.py`, and the eval replays.
Expected: PASS.

```bash
git add app/sample_run.py scripts/sample_snapshot.py tests/test_sample_run.py data/dev/sample-run.json app/api/runs.py app/api/gap.py app/api/schemas.py .vercelignore docs/CONTRACTS.md openapi.json web/src/lib/api-types.ts web/src/lib/api.ts web/src/views/RunGrid.tsx web/src/views/RunGrid.test.tsx
git commit -m "perf(sample): the sample company's questionnaire and core gap check are copied from a generated snapshot" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: The E2E suite re-recorded with the gap flow

**Runs on:** `plan6b`, after Task 7b, by the lead (database `vart_test_plan6b`). **Reviewer:** Opus. **Lead-run steps:** the recording and the cap measurement. **Eval key:** about $0.03. The sample flow and the core gap check are copied from the snapshot (Task 7b), so they make no model call. What is left:
- the upload flow, about $0.02;
- the interview and Govern re-checks, about $0.01;
- one live Recover part.

**Files:**
- Create: `web/e2e/gap.spec.ts`
- Modify: `web/e2e/recorded.jsonl`, deleted and recorded again by the lead's record run (never edited by hand)

**Interfaces:**
- Consumes:
  - everything from Tasks 1-7b (the lanes are merged in Task 7b Step 1);
  - `RUN_WAIT` and `xlsxCells` from `web/e2e/helpers.ts`;
  - the Workspace view's `l` (load the sample documents: rules classify all 23, so no model call).
- Produces: the E2E suite on one fresh recording, with one new flow. The flow:
  - starts a core gap check over the sample documents, which is copied instantly;
  - sees a stated non-compliance;
  - opens a Checked outcome's parts;
  - answers an Ask-me outcome (re-checked against Govern parts);
  - checks the exported gap report cell by cell;
  - runs the Recover scope live (one part), so the live runner is in the suite too.

- [ ] **Step 1: Write the flow**

`web/e2e/gap.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { RUN_WAIT, xlsxCells } from "./helpers.ts";

// The core gap check over the untouched sample pack is copied from data/dev/sample-run.json (Task 7b): no model
// call. Then at most 7 re-checks of Govern parts after the Ask-me answer, and one live part for the Recover scope.
// The whole suite stays near 55 model calls, far under the 400-an-hour per-network cap.
test("the gap check runs over the sample documents, takes an Ask-me answer and exports the report", async ({ page }) => {
  await page.goto("/?view=workspace");
  await expect(page.getByRole("button", { name: "Load sample documents" })).toBeEnabled();
  await page.keyboard.press("l");
  await expect(page.getByText("security-improvement-plan.md")).toBeVisible();
  await page.keyboard.press("6");
  await page.waitForURL(/view=gap/);
  await expect(page.getByText("checked 31 · ask me 5 · not checked 70 · of 106")).toBeVisible();
  await page.keyboard.press("r");
  await expect(page.getByText(/36 of 36 checked · done/)).toBeVisible({ timeout: RUN_WAIT });
  await expect(page.getByRole("row", { name: /^[A-Z]{2}\.[A-Z]{2}-\d\d / })).toHaveCount(106);
  // the planted improvement plan: at least one stated non-compliance shows
  const filters = page.getByRole("group", { name: "filter by label" });
  await expect(filters.getByRole("button", { name: /^not met [1-9]\d*$/ })).toBeVisible();

  // A Checked outcome: NIST's text and link, and its four parts
  await page.getByRole("row", { name: /^PR\.DS-11 / }).click();
  const drawer = page.getByRole("complementary");
  await expect(drawer.getByText("parts (4)")).toBeVisible();
  await expect(drawer.getByRole("link", { name: "NIST CSF 2.0 reference tool" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // An Ask-me outcome, answered in the inspector (re-checked against Govern parts; fills stay suggestions)
  await page.getByRole("row", { name: /^GV\.RM-02 / }).click();
  await drawer
    .getByLabel("your answer to GV.RM-02")
    .fill("Yes. The board approved a cybersecurity risk appetite statement, and the security team shares it with every new hire.");
  await drawer.getByRole("button", { name: "Send" }).click();
  await expect(drawer.getByText("confirmed by you").first()).toBeVisible({ timeout: RUN_WAIT });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("row", { name: /^GV\.RM-02 / })).toContainText("confirmed by you");

  // The gap report
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const saved = await download;
  expect(saved.suggestedFilename()).toBe("csf-2.0-core-gap-report.xlsx");
  const file = test.info().outputPath(saved.suggestedFilename()); // openpyxl needs the extension
  await saved.saveAs(file);
  const cells = xlsxCells(file, "Gap report", ["A1", "B1", "A2", "D2", "A3", "G3", "A110"]);
  expect(cells).toMatchObject({
    A1: "Possible gap — review it",
    B1: "Scope: core",
    A2: "ID",
    D2: "Label",
    A3: "GV.OC-01",
    A110: "Not legal advice. CSF 2.0 text © NIST, public domain.",
  });
  expect(cells.G3).toBe("The organizational mission is understood and informs cybersecurity risk management"); // verbatim

  // A function scope is not in the snapshot: it runs live through the concurrent runner (Task 2b)
  await page.keyboard.press("o");
  await page.waitForURL(/scope=recover/);
  await page.keyboard.press("r");
  await expect(page.getByText(/1 of 1 checked · done/)).toBeVisible({ timeout: RUN_WAIT });
});
```

- [ ] **Step 2: Run it against the old recording to verify it fails**

Run: `cd web && LLM_MODE=replay npx playwright test e2e/gap.spec.ts`
Expected: FAIL. The Govern re-checks and the live Recover step answer 500 on a `ReplayMiss`, because none of them is recorded yet.

- [ ] **Step 3 (lead): Record the whole suite again with the eval key**

The sample pack changed in Task 7 and the sample run is now copied (Task 7b), so most of the old recording is unused. The whole suite is recorded fresh; starting from an empty file leaves no stale rows.

First make sure no server is listening on port 8000: Playwright reuses an existing server outside CI, and a replay server would ignore record mode. Then:

```bash
cd web && rm -f e2e/recorded.jsonl && (set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" LLM_MODE=record npx playwright test)
```

Expected: every spec passes live in about 5 minutes (the upload flow's 20 items run four at a time, Task 2b), for about $0.03 of the eval key. Stop and ask Tarun if the key's remaining credit is under $1.

The core gap labels come from the snapshot (Task 7b). If its `not met` filter shows 0, the snapshot is valid evidence of a miss, not a test to loosen. Stop and report to Tarun with the two planted outcomes' labels (ID.RA-02, DE.AE-07).

- [ ] **Step 4 (lead): Replay the whole suite twice, measure the cap, scan the recording**

Run: `cd web && LLM_MODE=replay npx playwright test && LLM_MODE=replay npx playwright test`
Expected: PASS both times with no network.

Then read the per-network model calls the last run counted (the e2e server writes to `DATABASE_URL`):

```bash
python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); print(e.connect().execute(text(\"SELECT window_start, hits FROM ip_limits WHERE kind = 'llm' ORDER BY window_start DESC LIMIT 2\")).all())"
```

Expected: the latest window's hits are about 55 and under 400. That is the upload flow's about 40, the interview and Govern re-checks up to 15, and 1 Recover part; it was about 231 before Task 7b. If one suite run straddles an hour, add the two windows. Over 400 is a failure: report it to Tarun and do not raise the cap. Record the number in Task 9's PROGRESS entry.

Then run `gitleaks dir --redact --no-banner web/e2e/recorded.jsonl` (the `.gitleaks.toml` allowlist covers the 64-hex keys).
Expected: no leaks.

- [ ] **Step 5: Commit**

```bash
git add web/e2e/gap.spec.ts web/e2e/recorded.jsonl
git commit -m "test(e2e): the gap check flow; the suite re-recorded on the 23-document sample pack" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Adversary checkpoint 2, docs, final review and the release plan

**Runs on:** `plan6b`, by the lead. **Eval key:** none. **Outward steps:** Tarun's (push, PR, migrate, fast-forward `main`).

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md`, `docs/CONTRACTS.md` (fix-round lines only, if any)

- [ ] **Step 1 (lead): Adversary checkpoint 2**

Dispatch Fable 5.1 on `main..plan6b`: what input, label, lock order, copy, fill or coverage claim did everyone miss? Point it at this plan's Review Focus and at:
- the runner's resume path;
- `reopen_changed` against an accepted fill and an in-flight step;
- the function-wide fills (Review Focus 6);
- the gap sheet in a visitor's workbook (a sheet name clash, inert cells, the active sheet);
- the moved planted document's facts and keys;
- the inspector at 375px;
- the network budget.

Each accepted finding gets:
- a fix by the owning lane's implementer;
- a reviewer pass;
- a CONTRACTS.md change-log line when it touches the contract.

Re-run Task 8 Step 4 after any fix that changes what the E2E calls.

- [ ] **Step 2: Write the README section**

In `README.md`, replace the stale status line with `Status: live at https://vart-v2.vercel.app (Plans 1-3, 6).` and append:

```markdown
## Gap check (NIST CSF 2.0)

**What it is.** VART reads your documents against NIST's Cybersecurity Framework 2.0 and reports, outcome by
outcome, what they show: **Covered**, **Partly covered**, **Not met (stated)** when a document says a part is not
done, **Documents disagree**, or **Gap** when nothing speaks to it. Each checked outcome is cut into NIST's own
parts; every part is asked as a question through the same engine that fills questionnaires, and code combines
the parts' labels and writes the explanation. Every finding quotes your line next to NIST's verbatim text and
links to NIST, with the related SP 800-53 Rev 5 controls. The report exports as a gap-report sheet, alone or
inside your filled questionnaire. The sample company's documents include an improvement plan that states two
controls are not in place yet, so the demo shows what a stated non-compliance looks like. "Try with a sample
company" opens at once and spends nothing: it copies a run the same engine made over the same sample documents
(`data/dev/sample-run.json`, regenerated whenever a prompt, a model or a sample document changes). "Re-run live"
runs the engine for real.

**What it is not.** It is not legal advice, an audit, a certification or a compliance score, and no overall score
is shown. Every finding reads "possible gap, review it". It checks 31 of CSF 2.0's 106 outcomes against documents,
asks you about 5 governance outcomes that documents rarely state, and lists the other 70 as not checked in this
version. A checked outcome is judged on documents only: your answers confirm the Ask-me outcomes, and can fill a
checked part in the same CSF function only as a suggestion you accept. On the dev pack its outcome labels agree
with a blind judge's key 22 times in 31 (0.71 against a 0.80 target, reported in `evals/results/gap-dev.md`).

Not legal advice. CSF 2.0 text © NIST, public domain.
```

- [ ] **Step 3: Update `CLAUDE.md` and the CSF spec**

`CLAUDE.md` Map:
- add `app/api/gap.py` (gap-check endpoints) to the API line;
- in the UI line, add `GapCheck.tsx` and `GapDrawer.tsx` (the Gap check view and its inspector) after `web/src/views/`;
- in the Engine line, after `app/csf.py ...`, add "; `app/runs.py` answers a gap-check run part by part (`run_items.parts`)";
- in the data line, `data/dev/gap/` becomes "the gap check's outcome map and judged overrides; the planted improvement plan is in the dev pack", and add "`data/dev/sample-run.json` the precomputed sample run (`app/sample_run.py`; regenerate with `scripts/sample_snapshot.py`, lead only, eval key)";
- in the Engine line, add "a step answers its claimed items at once, one session per worker (Task 2b)".

Commands:
- the E2E line keeps "re-record with ... `rm -f e2e/recorded.jsonl` and `LLM_MODE=record npx playwright test`";
- add "Sample snapshot: when `tests/test_sample_run.py::test_the_sample_snapshot_is_current` fails, the lead runs the command in `scripts/sample_snapshot.py`'s docstring".

The CSF spec:
- under 5.6, add: `Sync (Plan 6B, Tarun 2026-10-06; adversary-1 I3, I4): in a gap-check run an Ask-me answer is re-checked against the open parts of Checked outcomes in the same CSF function (a questionnaire keeps the same-topic rule), at most 8 re-checks per answer; a fill stays a suggestion until accepted, then reads "Confirmed by you: part n", and the outcome reads Confirmed by you once every part that is not a Gap was filled. Check again (r) re-runs every machine-judged part of each affected outcome; an outcome is affected when a part's passages (as a set, statements left out of the top 8), wording, stance prompt or model changed; a part the visitor filled stays.`
- under section 7, add: `Sync (Plan 6B): the path's first segment is "workspace" (the API has no company name); the filter toggles have no single keys; the coverage line sits in the status line; 800-53 controls link to NIST's SP 800-53 Rev 5 page; the gap sheet also rides in an xlsx questionnaire export (the latest done gap check, with its scope and date).`
- under section 8, add: `Sync (Plan 6B, Tarun 2026-10-06): the planted improvement plan moved from the gap extension into the dev pack, which is the sample pack, so the live demo shows Not met (stated). The questionnaire keys were re-derived and the dev eval re-recorded; its gates held.`
- add a change-log line: `2026-10-06: Plan 6B sync (sections 5.6, 7 and 8): fills within a CSF function and Confirmed by you per part, check again on sets of passages, the gap sheet in questionnaire exports, the planted plan in the sample pack.`

The main spec (`docs/superpowers/specs/2026-10-03-vart-v2-design.md`):
- in sections 9 and 11.1, where the precomputed sample run is planned for Plan 4, add: `Sync (Plan 6B Task 7b, Tarun 2026-10-06): the precomputed sample run moved into Plan 6B. It covers the sample questionnaire and the core gap check over the untouched sample pack, copied from data/dev/sample-run.json, which the lead generates with the eval key; a stale snapshot is never used.`
- in 6.3, add: `Sync (Plan 6B Task 2b): a step answers its claimed items at the same time, one session per worker; the step's guarantees are unchanged.`
- add a change-log line for both.

- [ ] **Step 4: Update `docs/PROGRESS.md`**

- At a glance:
  - the 6A row reads `done, live`;
  - add a row `| 6B CSF gap check, the visitor half | done on plan6b; release pending | Gap check view (tab 6), per-part runner and resume, concurrent steps (64 items <t1> s, core gap run <t2> s, measured in Task 7b Step 6), the precomputed sample run, check again per affected outcome, Ask-me answers filling Govern parts, gap sheet in both exports, the planted plan in the sample pack, one E2E flow (<N> model calls per full suite) |`;
  - the Plan 2 row's dev baseline gets the re-recorded numbers ("re-recorded 2026-10-06 with 23 documents: label accuracy <x>, ...").
- Decisions, dated the merge day:
  - the per-part migration (two columns, no table);
  - check again re-runs every part of each affected outcome, started by `r`, never by an upload;
  - the gap sheet goes in both exports;
  - controls link to one NIST page;
  - the planted improvement plan joins the sample pack (Tarun), which reverses the 6A decision that kept it gap-only; the dev keys were re-derived and the dev gates held at their values;
  - fills widen to the same CSF function (Tarun), and an accepted fill reads Confirmed by you, never Covered (adversary-1 I3);
  - the filter toggles have no keys;
  - a step answers its claimed items concurrently (Tarun; Task 2b);
  - the precomputed sample run and core gap check (Tarun; Task 7b);
  - `retrieve` gains `exclude_kinds` (Ruling 4, rule 10).
- "Plan 4 carry-over": remove "The sample run is not precomputed yet; the cheapest way is to replay the dev recordings for `source = sample` runs." (done in 6B Task 7b).
- "6B carry-over":
  - mark (a), (b), (c) and (d) done, each with its task;
  - mark "`app.csf.evidence` drops statements after the top-8 cut" done (Task 4, `exclude_kinds`);
  - keep "Stance improvement" carried to a later plan.
- Under Releases, add `### Plan 6B`, `_Filled in after the release (Step 8)._`

- [ ] **Step 5: Run every chain once more and commit**

Run: the backend chain, the frontend chain, `python -m datakit.validate all`, `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`, and `cd web && LLM_MODE=replay npx playwright test`.
Expected: PASS.

```bash
git add README.md CLAUDE.md docs/PROGRESS.md docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md docs/CONTRACTS.md
git commit -m "docs(csf): Plan 6B readme section, map, spec sync and progress" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6 (lead): Final Opus review**

An Opus reviewer reads `main..plan6b` against this plan, the CSF spec sections 5, 7, 8 and 11, and the Review Focus. Fix rounds follow its findings; then re-run Step 5's chains.

- [ ] **Step 7 (lead → Tarun): The release plan**

Send Tarun this plan. Every step is his; the lead runs nothing outward.
1. Push `plan6b` and open a pull request to `main`.
2. Wait for green CI: gates, backend (with the dev and gap-dev replays), frontend, e2e.
3. From the branch head, run `ops/setup.sh migrate`: Neon goes `a7c3e9d1b2f4` → `c4e8a2d6f1b3` before `main` moves, because Vercel deploys `main` at once. The migration is additive, and the live code ignores both columns. To roll back after the first gap-check answer in production, roll back the code only, never `alembic downgrade` (its refusal is by design; adversary-1 M11).
4. Fast-forward `main` to `plan6b` and push. Vercel deploys.
5. Check on https://vart-v2.vercel.app that:
   - the smoke test passes and `/api/health` reads `"status":"ok"`;
   - the sample pack lists 23 documents;
   - "Try with a sample company" opens a done run at $0.0000, marked precomputed;
   - the Gap check tab's core check is done at once.

   If the sample run starts running instead, production's models or prompts differ from the snapshot's digest. The run then goes live, safely, until the lead regenerates the snapshot.

Two data files are new in the function bundle: `data/dev/docs/security-improvement-plan.md` (2 KB) and `data/dev/sample-run.json`, under 1 MB (checked in Task 7b Step 6). That is far under the bundle's headroom, so no preview check is needed.

- [ ] **Step 8 (lead): The release record**

After Tarun's step 5, fill `### Plan 6B` in `docs/PROGRESS.md`:
- `main` = `<sha>`, merged by PR `#<n>` after green CI;
- the migration;
- the smoke and health results;
- the E2E's model calls per suite;
- the re-recorded dev numbers;
- Task 7b Step 6's two run times and snapshot cost.

Commit it on `plan6b-record` from the new `main`, with the trailer. Pushing it is Tarun's.

---

## Self-review notes (for the lead)

- **Spec coverage.**
  - 5.1 (start a run per scope, the same run machinery, caps and expiry): Task 3 `start_gap`, through `create_run`, `limit("run")`, `ensure_capacity` and the existing step endpoint; one run per first press (I2).
  - 5.2-5.3 (part by part, labels combined by code): Tasks 2 and 2b; Confirmed by you per part, Task 4 (I3).
  - 5.4 (Ask-me redacted, stored, Confirmed by you, Not answered): Task 2 `ASK`, Task 4 `ensure_questions` and `test_an_ask_me_answer_is_redacted_stored_and_confirmed`, Task 3 `gap_rows`, Task 6 answer box.
  - 5.5 (not checked: no call, no label): Task 3 view test, Task 5 rows; N/A on either tier (I1, consumed in Tasks 3, 5, 6).
  - 5.6 (re-check per part, every part of each affected outcome; an accepted fill replaces one part before combine; fills within a CSF function): Task 4.
  - 5.7 (claim by parts at most 8, resume after a refusal, spend before every call, no open transaction): Tasks 2 and 2b.
  - 6 (no schema change beyond the one migration): Task 1. Tasks 2b and 7b add none.
  - 7 (tab 6, path, scope keys, r, e, filter counts, grouped 28px rows, inspector with NIST text, link, controls, explanation, footnoted sources, line listings, dropped evidence, Ask-me box, status line, export columns in both exports, copy): Tasks 3, 5 and 6.
  - 8 (planted cases visible in the demo; the E2E): Tasks 7, 7b and 8.
  - 11 (view, export, README): Tasks 3-9.
  - Main spec 6.3 (step runner, faster) and 9/11.1 (the precomputed sample, moved from Plan 4): Tasks 2b and 7b, with sync lines in Task 9.
  - Carries (a)-(d): Tasks 2, 2, 4 and 3+6. Ruling 5 (csf questionnaires not counted, listed or deleted) was already in Plan 3's code; Task 3 pins listing.
  - Adversary checkpoint 1 (Ruling 4) is folded in:
    - I2 → Task 3; I3 and I4 → Task 4; M1 → Task 4; M2, M4, M6 and M8 → Task 3;
    - M3 → moot in Task 2b; M5 → Tasks 2, 2b and 4; M7 → Task 5; M9 → Task 6; M10 → Task 7; M11 → Task 9;
    - I1 stays a Task 1 fix-round item, and Tasks 3, 5 and 6 consume `GapRow.not_applicable`.
- **Placeholders.**
  - "<keep the existing docstring>" (Tasks 2 and 4) and "<the docstring of the committed stub in app/api/gap.py, unchanged (Ruling 2)>" (Task 3) name text that already exists.
  - `<N>`, `<x>`, `<t1>`, `<t2>`, `<sha>` and `<n>` in Task 9 are numbers only the runs and the release produce.
- **Type consistency.**
  - `check_part(session, workspace_id, o, n, llm, models, spend)` is the same in Tasks 2-4 and 2b.
  - `_is_current(o, n, raw, models)` is defined in Task 2 and used by Task 2b's `_keep_current_parts` and Task 4's `_same_evidence`.
  - `part_result(o, n, raw)` and `outcome_values(o, parts)` (parts keyed `"1"`..`"n"`) are the same in Tasks 2, 2b, 3 (`_parts`) and 4 (`_fill_part`, `_redecide_parts`).
  - `reopen_changed(session, workspace_id, run_id, models=None) -> int` is the same in Task 4 and its CONTRACTS line.
  - `explain(o, parts, filled=frozenset())` and `aggregate(o, parts, filled=frozenset())` are the same in Task 4 and `outcome_values`.
  - `retrieve(..., *, exclude_kinds=())` is the same in Task 4 and `csf.evidence`.
  - `gap_rows(session, scope, q, run)` feeds `gap_view` and `gap_sheet`, and `gap_sheet(session, q, run) -> GapSheet` feeds `gap_report(g)` and `export_xlsx(..., gap)`.
  - `GapSheet(rows, citations, run_date, scope, version, controls_url, statement_docs=frozenset())` has the same field order in its tests and its builder.
  - `copy_questionnaire_run(session, workspace_id, questionnaire_id, models)` and `copy_gap_run(session, workspace_id, q, models)` are the same in Task 7b's endpoints.
  - `sample_run.swap(values, chunk, doc)` is used by the script and `_copy`; `ANSWER_FIELDS` are the 11 keys `_raw` writes.
  - `_same_area(asked, item)` is only in `app/questions.py`.
  - On the frontend, `GapRow` (with `not_applicable`), `GapOut`, `PartOut`, `GapLabel`, `GapScope` and `RunOut.precomputed` come from the generated types; `GapChip` takes `GapLabel`, and `PartOut.label` is assignable to it.
- **Counts that tests pin:**
  - 106 outcomes, 31 / 5 / 70 tiers, 36 items in the core run, 73 parts;
  - Recover's one in-scope outcome (RC.RP-01) and PR.DS-11's four parts;
  - the first core step taking GV.OC-03, GV.RM-02, GV.RR-02 and GV.PO-01 (1 + 1 + 1 + 3);
  - 7 Govern re-checks (GV.PO-01's 3 and GV.PO-02's 4);
  - the gap report's footer at row 110 for the core;
  - 23 sample documents;
  - 64 snapshot questionnaire items and 36 snapshot gap items.

  A tier change moves the CSF counts together (6A self-review), the sample count moves with `data/dev/facts.yaml`, and any of them moves the snapshot digest.
- **Review Focus.** Each of the eight lines has its test in the owning task. Three failure modes outside them are noted and accepted:
  - two steps on one stale claim (Plan 4 carry N1) could store one part twice; the later write wins, and nothing is charged twice beyond what N1 already allows;
  - a withdrawn NIST id in an old run ends at `MAX_ATTEMPTS` (the `ponytail:` comment in Task 2b's `step`);
  - a step opens up to 9 Postgres connections (NullPool, one per worker), which production's pooled Neon URL absorbs.
