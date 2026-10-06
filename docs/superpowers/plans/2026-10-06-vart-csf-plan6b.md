# VART - Plan 6B: CSF 2.0 gap check, the visitor-facing half Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A visitor runs NIST's CSF 2.0 gap check over their own documents from a Gap check view: they start a run per scope and check it again after an upload, answer the Ask-me outcomes, inspect each outcome part by part next to NIST's text and the cited lines, and export a gap-report sheet. Every label is decided by code.

**Architecture:** Part 0 (Task 1) adds one additive migration (`run_items.parts`, `suggestions.part`) and freezes the contract additions: two paths under `/api/gap/{scope}` (answering 501 until built), the optional fields `AnswerDetail.parts` and `SuggestionOut.part`, and the new `app/csf.py` signatures in `docs/CONTRACTS.md`. After adversary checkpoint 1, two lanes run in parallel on disjoint files:
- **api** (Tasks 2-4): the step runner answers csf items part by part, claiming outcomes until their parts reach 8 and storing each part's result as it lands; the gap endpoints, the inspector's parts and the gap-report sheet; the re-check after an upload or an answer, and re-decide per part.
- **ui** (Tasks 5-6): the Gap check view (tab 6) and its inspector, built against the generated types and the fetch mock.

The lead merges both lanes into `plan6b` and adds one Playwright flow on recorded replies (Task 7). The whole-branch adversary checkpoint, the docs, the final review and the release plan follow (Task 8). Decide, stance, the draft prompt, retrieval and `answer_retrieved` do not change, so no eval is re-recorded.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic (JSONB), openpyxl, pytest with Postgres; React 19 + Vite + TypeScript + Tailwind v4, Vitest + Testing Library, Playwright with `LLM_MODE=replay`.

**Spec:** `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md`: sections 5 (5.1 start, 5.4 Ask me, 5.5 not checked, 5.6 per-part re-check, 5.7 cost and claim rule), 7 (view, export, copy), 8 (the E2E side only) and 11 (definition of done). It sits on the main spec `docs/superpowers/specs/2026-10-03-vart-v2-design.md`: 6.3 step runner, 6.7 re-decide, 6.9 interview, 6.10 export, 6.12 API.

Other inputs:
- the 6A plan `docs/superpowers/plans/2026-10-05-vart-csf-plan6a-backend.md` (Task 8 and its 6B carries);
- `docs/PROGRESS.md` ("6B carry-over" (a)-(d));
- the lead's 6A ledger, Rulings 14-21;
- `design.md` (direction C, binding for UI);
- `docs/CONTRACTS.md` (the frozen HTTP contract: changes may only add optional fields, paths or statuses, each with a change-log line).

## Execution notes (read first)

- **Branches and worktrees.** Integration branch `plan6b` in `~/Desktop/portfolio/projects/VART-wt-plan6b`, from released `main` at `d071aa2` (Plans 3 and 6A live; Neon at `a7c3e9d1b2f4`). Part 0 (Task 1) runs there. After adversary checkpoint 1 the lead creates two lane worktrees from `plan6b`: `plan6b-api` in `~/Desktop/portfolio/projects/VART-wt-6b-api` (Tasks 2-4, in order) and `plan6b-ui` in `~/Desktop/portfolio/projects/VART-wt-6b-ui` (Tasks 5-6, in order). The lead merges both into `plan6b` (Task 7). Test databases: `vart_test_plan6b` (Part 0, integration, E2E) and `vart_test_6b_api` (api lane). The lead creates each once from the main checkout: `docker compose exec db createdb -U vart <name>`. The ui lane needs no database.
- **Decisions this plan takes.** Tarun confirms them when he reviews the plan:
  1. **One migration, additive** (`c4e8a2d6f1b3`). Carry (a) needs somewhere to keep a part's result before its outcome is whole, and carry (c) needs a fill to name its part. Two columns do it and no table: `run_items.parts JSONB NOT NULL DEFAULT '{}'` (keys `"1"`..`"n"`, each the part's stored result plus its wording) and `suggestions.part SMALLINT NOT NULL DEFAULT 0` (0 is a whole item), with `uq_suggestions_fill` widened by `part`. Old code runs on the new schema unchanged, so Tarun migrates Neon before `main` moves, as for every release.
  2. **Where the parts live.** A part's stored result is `{"question": <part wording>, **runs._raw(result)}`, plus `"statement_id"` when an accepted fill wrote it. The `answers` row stays the outcome's display record (CSF spec 5.3). Its `chunk_ids` are the union of the parts' chunk ids, so `redecide` still finds it, and it has no stances of its own.
  3. **Check again re-runs only the parts whose evidence changed.** The trigger is `r` on a scope whose run is done (`POST /api/gap/{scope}/run`). A part counts as changed when its retrieval (no model call) now returns other passages than it was judged on, or when its wording changed. Spec 5.6's last bullet says a new upload re-runs every part of an affected outcome; this narrows it to the changed parts. An unchanged part sends the same prompt, so re-running it can change nothing in replay and only costs a call live. A sync line goes into the spec (Task 8). An upload never starts model calls by itself: the view offers "Check again".
  4. **Paths.** `GET /api/gap/{scope}` and `POST /api/gap/{scope}/run`. `Mapping.scope`, kept free in Plan 3 for 6B, stays unused, because `GapOut.scope` and the questionnaire's stored mapping carry the scope.
  5. **Export.** The gap report is what `GET /api/runs/{id}/export` returns for a gap-check run. That path answered 409 for such a run before (it has no file), so the change adds a status there. A questionnaire run's export does not change (open question 1).
  6. **800-53 controls** link to one NIST page (`csf.CONTROLS_URL`), not one page per control. As with 6A's decision 3, no per-control URL could be verified (the Reference Tool's deep links are single-page-app routes). The lead checks the URL in a browser in Task 1 Step 7.
  7. **The sample pack stays as it is.** It does not gain the gap extension's `security-improvement-plan.md`: adding it would change the dev pack's retrieval and force a re-record. So the live demo shows no Not met (stated) unless the visitor uploads such a line (open question 2).
  8. **Per-part fills after an Ask-me answer** are built and tested (carry c), but today the same-topic rule (spec 6.9) never pairs them. No v1 Ask-me outcome shares a CSF category with a Checked one: the Ask-me categories are GV.OC, GV.RM, GV.RR, GV.OV and GV.SC, and the only Checked Govern category is GV.PO. The fills work as soon as the tiers pair. The test sets one topic by hand (open question 3).
  9. **Questions for you on a gap-check run holds its Ask-me outcomes only** (6A decision 6, now enforced in `ensure_questions`). As for any run, they are planned once the run is done.
  10. **The view's path is `workspace / csf 2.0 / <scope>`.** The API has no company name for spec 7's `<company>`.
  11. **The gap view's filter toggles have no single keys.** `g i p d s o a r e` are taken, and spare letters would read as noise. The toggles are Tab-reached buttons, like the Workspace row actions; design.md gets a line.
- **Network budget for the E2E.** The CI suite shares one per-network cap of 400 model calls an hour. Plan 3's specs use about 150. The gap flow runs one core check over the sample documents: at most 73 stance calls (one per part with passages), no draft call, and no recheck call, because the Ask-me answer's topic pairs with no Checked outcome (note 8). Total about 223. Task 7 Step 5 measures it from `ip_limits` after a full replay.

## Lanes

| Part | Tasks | Runs on | Implementer | Reviewer |
|---|---|---|---|---|
| Part 0: migration and contract additions | 1 | `plan6b` | lead (Opus 5.5) | Opus |
| Lane api | 2, 3, 4 | `plan6b-api` | Opus 5.5 (2, 4), Sonnet 5.5 (3) | Opus (2, 4), Sonnet (3) |
| Lane ui | 5, 6 | `plan6b-ui` | Opus 5.5 | Opus |
| Integration and E2E | 7 | `plan6b` | lead | Opus |
| Checkpoint, docs, release | 8 | `plan6b` | lead | final Opus review; Tarun approves every outward step |

The lanes share only Task 1's frozen output (`openapi.json`, `web/src/lib/api-types.ts`, the migration), so their files are disjoint. Inside the api lane, Task 3 calls Task 2's runner and Task 4 changes Task 3's POST handler, so those three run in order. Inside the ui lane, Task 6 renders its drawer inside Task 5's view.

## Global Constraints

- Every commit message ends with exactly this paragraph: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (also when a Sonnet model commits).
- Never open, list, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/`; never type the sponsor's company or people names.
- Never use `git stash`. Set work aside with a WIP commit on your own branch.
- Tests never touch the network or a real key (pytest-socket): model calls go through `tests/fakes.py` (`FakeLLM`, `ByStepLLM`). The E2E replays `web/e2e/recorded.jsonl`; only the lead records, with the eval key, and only in Task 7.
- Backend chain, green before every commit (run `ruff format .` first; with `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/<lane db> && export DATABASE_URL=$TEST_DATABASE_URL`): `ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check`. Never run `docker compose` from a worktree.
- Frontend chain: `cd web && npm run lint && npm test && npm run build`, then `python scripts/check_monochrome.py` from the repo root.
- After any change to `app/api/schemas.py` or a route: `python scripts/export_openapi.py && (cd web && npm run gen:api)`, and commit both files. No hand-written request or response type under `web/src`.
- Hard rule 11: engine code spends the budget before every model call and holds no database transaction across one. Each part reaches a model only through `app.csf.check_part` → `answer_retrieved`. Ask-me and not-checked outcomes make no model call (CSF spec 5.4-5.5).
- `ck_answers_cited` is unchanged: no Covered or Partly covered result without a citation (CSF spec 6).
- Frozen, never edited by a task: `app/text.py`, `app/patterns.py`, `app/contracts.py`, `app/decide.py`, `app/stance.py`, `app/draft.py`, `app/pipeline.py`, `app/retrieve.py`, `app/interview.py`, `app/ingest/`, `app/redact.py`, every prompt, `data/`, `evals/`. After adversary checkpoint 1, the Task 1 additions to `app/api/schemas.py` and every path, method and status in `openapi.json` are frozen too; a change needs the lead's OK and a change-log line in `docs/CONTRACTS.md`.
- The evals do not move: `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results` passes after every api-lane task.
- CSF spec 4: "What the visitor sees as 'the framework' is always NIST's verbatim `outcome` text." The view, the inspector and the export show `outcome` unedited.
- CSF spec 5.5: "Not-checked outcomes make no model call and carry no label." CSF spec 2: "Every finding reads 'possible gap, review it'; the view and the export say so."
- Copy, exactly (CSF spec 7): `Possible gap — review it` and `Not legal advice. CSF 2.0 text © NIST, public domain.` (an em dash, and the © sign).
- The status line counts tiers from the rows and is never typed in. For the core it reads `checked 31 · ask me 5 · not checked 70 · of 106`.
- Monochrome UI only: black, white and `neutral-*` (`scripts/check_monochrome.py`); labels in words, never colour alone; design.md direction C components (28px rows, filter line, command line, inspector drawer, key hints).
- Production migrations run from Tarun's terminal (`ops/setup.sh migrate`), never in a build or by an agent; the migration reaches Neon before `main` moves.
- The eval key (`VART_EVAL_OPENROUTER_API_KEY` in `~/.config/vart/eval.env`) is loaded inside the command and never printed; spending past its $5 cap needs Tarun.
- Each task owns the files it lists; the reviewer rejects edits outside them. The same failure twice: stop and report. Never weaken, skip or delete a test.

## Review Focus

1. **A step refused by the hourly stance cap in the middle of an outcome.** A second core run in the same hour does this (CSF spec 5.7). Expect: the parts already paid for stay stored; no answer row appears until every part is there; the next step pays only for the parts still missing; each paid call is counted once in `runs.cost_usd`. Pinned in Task 2 (`test_a_refused_budget_keeps_the_paid_parts_and_the_next_step_pays_only_the_rest`).
2. **A metadata override after a gap run** (a document marked draft or not evidence). Expect: each part is decided again from its own stored stances, then the parts are combined again. Decide must never run over the outcome row's empty stances, which would turn every outcome into Gap. A part filled by an accepted fill keeps its result. Pinned in Task 4 (`test_a_metadata_override_redecides_each_part_and_recombines`).
3. **`r` pressed again on a done scope**, with or without a new upload, or pressed in two tabs at once. Expect: only the parts whose evidence changed run again. The visitor's edited, approved, confirmed or not-applicable outcomes and accepted parts stay. With nothing changed the run stays done and no model is called. Two presses re-open an outcome once. Pinned in Task 4 (`test_check_again_reruns_only_the_parts_whose_evidence_changed`, `test_check_again_keeps_the_visitors_outcomes_and_accepted_parts`, `test_check_again_with_nothing_changed_stays_done`, `test_check_again_after_an_upload_reopens_only_what_the_new_document_reaches`).
4. **A deploy rewords a part** while results for the old wording are stored, mid-run or after. Expect: a stored part whose wording differs from the deployed one runs again; the others are kept. Pinned in Task 2 (`test_a_stored_part_with_other_wording_is_run_again`).
5. **Coverage overstated in the view or the export.** That would be a label on a not-checked outcome, an unanswered Ask-me outcome shown as anything but Not answered, counts typed in, or an export that leaves out unchecked outcomes. Expect: labels come only from `csf.gap_label`; the status line is counted from the rows; the export lists every outcome in scope, the unchecked ones as "Not checked in this version". Pinned in Task 3 (`test_the_view_lists_every_outcome_and_labels_only_what_was_checked`, `test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells`) and Task 5 (`it("counts the coverage line from the rows")`).

## Review gates (run by the lead)

- **Adversary checkpoint 1** (Fable 5.1) after Task 1, before the lane worktrees exist. It reads the migration, the schema additions, the stubs, `openapi.json`, the CONTRACTS.md lines and this plan's Tasks 2-6, and asks:
  - what does the view or the inspector need that no field carries;
  - what can a visitor trigger that has no error shape;
  - can a stored part outlive the documents or the wording it describes;
  - does any path let an Ask-me answer or a not-checked outcome reach a model?
  Fixes land in Part 0, with the types regenerated, before the lanes start.
- **Two-failure rule**: the same failure twice in a task stops it for a Fable look.
- **Adversary checkpoint 2** (Fable 5.1) on `main..plan6b` after Task 7 (Task 8 Step 1): what input, label, lock order or copy did everyone miss? Fixes land before the docs and the final review.
- **Final Opus review** of `main..plan6b` after Task 8 Step 6. Pushing, the pull request, the migration and the fast-forward of `main` are Tarun's.

## File Structure

```
migrations/versions/c4e8a2d6f1b3_csf_parts.py   NEW (T1)  run_items.parts, suggestions.part, widened uq_suggestions_fill
app/db/models.py                                MOD (T1)  RunItem.parts, SuggestedFill.part
app/api/schemas.py                              MOD (T1)  GapRow, GapOut, PartOut; AnswerDetail.parts; SuggestionOut.part
app/api/gap.py                                  NEW (T1 stubs, T3 built, T4 check again)
app/main.py                                     MOD (T1)  include the gap router
openapi.json, web/src/lib/api-types.ts          GEN (T1)  regenerated
docs/CONTRACTS.md                               MOD (T1, T8)
tests/test_models.py, tests/test_openapi.py     MOD (T1)
app/csf.py                                      MOD (T2 current_mapping, check_part, part_result; T3 CONTROLS_URL)
app/runs.py                                     MOD (T2 per-part runner, outcome_values; T4 reopen_changed)
tests/test_csf_parts.py                         MOD (T2)
tests/test_runs_csf.py                          NEW (T2, T4)
app/api/answers.py                              MOD (T3)  AnswerDetail.parts
app/export.py, app/api/export.py                MOD (T3)  the gap-report workbook
tests/test_api_gap.py                           NEW (T3, T4)
tests/test_export.py                            MOD (T3)
app/questions.py, app/api/questions.py          MOD (T4)  Ask-me only; per-part fills; accept per part
app/redecide.py, tests/test_redecide.py         MOD (T4)  re-decide per part
tests/test_questions_csf.py                     NEW (T4)
web/src/lib/{api,route,labels}.ts               MOD (T5)
web/src/components/{ui,Shell}.tsx               MOD (T5)  GapChip; tab 6; key sheet lines
web/src/App.tsx                                 MOD (T5)
web/src/views/GapCheck.tsx (+ .test.tsx)        NEW (T5), MOD (T6)
web/src/test/mockApi.ts                         MOD (T5, T6)
design.md                                       MOD (T5)
web/src/views/EvidenceDrawer.tsx                MOD (T6)  DrawerFrame and DroppedList extracted, behaviour unchanged
web/src/views/Questions.tsx                     MOD (T6)  QuestionCard exported
web/src/views/GapDrawer.tsx (+ .test.tsx)       NEW (T6)
web/e2e/gap.spec.ts                             NEW (T7)
web/e2e/recorded.jsonl                          MOD (T7, appended by the lead's record run)
README.md, CLAUDE.md, docs/PROGRESS.md, the CSF spec   MOD (T8)
```

---

### Task 1: Migration and contract additions (Part 0)

**Runs on:** `plan6b`, by the lead. **Reviewer:** Opus. **Then:** adversary checkpoint 1.

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
    the done one with every part whose evidence changed since (a new upload) re-opened; with nothing changed it
    stays done and no model is called. 429 per network (`run`, 20 an hour); 503 when the demo is full."""
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
  every part whose evidence changed re-opened (`app.runs.reopen_changed`; none changed: it stays done). It is
  counted under `run`, and 503 when the demo is full. A step claims csf items until their parts add up to
  `STEP_PARTS` (8) and stores each part's result in `run_items.parts` as it lands. `AnswerDetail.parts` lists a
  Checked outcome's parts; `SuggestionOut.part` names the part a fill is for (0: the whole item). On a gap-check
  run, `GET /api/runs/{id}/export` answers the gap-report workbook (it was a 409), and Questions for you holds
  the Ask-me outcomes only. `Mapping.scope` stays unused.
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

Dispatch Fable 5.1 on `main..plan6b` with this plan's Tasks 2-6 and the questions under "Review gates". Fix its findings in Part 0, regenerate the types, add change-log lines, and commit. Then create the two lane worktrees from `plan6b` (Execution notes).

---

### Task 2: The step runner answers a gap-check run part by part

**Lane:** api, worktree `VART-wt-6b-api`, database `vart_test_6b_api`. **Implementer:** Opus 5.5. **Reviewer:** Opus (budget, transactions, resume).

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
  - A stored part is `{"question": str, "label", "value", "text", "citations", "dropped", "conflict", "scope_note", "confidence", "stances", "chunk_ids", "retrieval_dropped"}` (the keys of `runs._raw`), plus `"statement_id": str` when an accepted fill wrote it (Task 4).

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
    a step refused by the budget mid-outcome resumes without paying again. A stored part whose wording differs
    from the deployed one runs again. Then code combines the parts (`outcome_values`)."""
    # ponytail: an id NIST withdrew in a data refresh is a KeyError here; the step's crash path ends the item
    # at MAX_ATTEMPTS. A refresh changes the digest, so only a run started before the deploy can meet one.
    o = csf.framework().get(row.csf_id or "")
    if o.tier != "checked":
        return dict(ASK)
    have = session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == row.id)) or {}
    parts = {str(n): have[str(n)] for n, text in enumerate(o.parts, 1) if have.get(str(n), {}).get("question") == text}
    session.commit()  # no transaction stays open into the first model call
    for n, text in enumerate(o.parts, 1):
        if str(n) in parts:
            continue
        call = partial(csf.check_part, session, workspace_id, o, n, llm, models, spend)
        parts[str(n)] = _no_nul({"question": text, **_raw(_once(session, call, can_retry))})
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

### Task 3: The gap endpoints, the inspector's parts and the gap-report sheet

**Lane:** api (after Task 2). **Implementer:** Sonnet 5.5. **Reviewer:** Sonnet (Opus looks at the export's inert cells in checkpoint 2).

**Files:**
- Modify: `app/csf.py` (`CONTROLS_URL`), `app/api/gap.py` (replace the stubs), `app/api/answers.py` (`_dropped`, `_parts`, `detail`), `app/export.py` (`gap_report`), `app/api/export.py` (gap-check runs)
- Create: `tests/test_api_gap.py`
- Modify: `tests/test_export.py`

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
  - `app.export.gap_report(rows: list[GapRow], citations: dict[uuid.UUID, list[dict[str, Any]]], run_date: str, version: str, controls_url: str) -> bytes`
  - `app.export.REVIEW`, `FOOTER`, `GAP_SHEET = "Gap report"`, `GAP_HEAD`
  - The built `GET /api/gap/{scope}` and `POST /api/gap/{scope}/run` (Task 4 adds check again to the POST)

- [ ] **Step 1: Write the failing API tests**

Create `tests/test_api_gap.py`:

```python
import io
import json
import uuid
from datetime import timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import csf
from app.api.deps import get_llm
from app.db.models import DocumentLine, Questionnaire, Workspace
from app.export import FOOTER
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
```

Append to `tests/test_export.py`, adding `uuid`, `from typing import Any`, `from app.api.schemas import GapRow` and `from app.export import FOOTER, GAP_HEAD, REVIEW, gap_report` to its imports:

```python
def _gap_row(csf_id: str, tier: Any, label: Any, explanation: str | None, answer_id: Any = None) -> GapRow:
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
    )


def test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells() -> None:
    aid = uuid.uuid4()
    cite = {"quote": "=cmd|' /C calc'!A0", "filename": "backup-policy.docx", "line_start": 2}
    rows = [
        _gap_row("PR.DS-11", "checked", "covered", "=SUM(A1)", aid),
        _gap_row("PR.DS-10", "not_checked", None, None),
        _gap_row("PR.DS-01", "checked", None, None),  # not answered yet
    ]
    body = gap_report(rows, {aid: [cite]}, "2026-10-06", "2.0", "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final")
    ws = openpyxl.load_workbook(io.BytesIO(body))["Gap report"]
    assert ws["A1"].value == REVIEW == "Possible gap — review it"
    assert tuple(c.value for c in ws[2]) == GAP_HEAD
    assert [ws.cell(n, 4).value for n in (3, 4, 5)] == ["Covered", "Not checked in this version", "Not run yet"]
    assert (ws["E3"].value, ws["E3"].data_type) == ("=SUM(A1)", "s")
    assert (ws["F3"].value, ws["F3"].data_type) == ("\"=cmd|' /C calc'!A0\" (backup-policy.docx line 2)", "s")
    assert (ws["G3"].value, ws["I3"].value, ws["J3"].value, ws["K3"].value) == (
        "NIST text of PR.DS-11", "CP-09", "2026-10-06", "2.0"
    )
    assert ws["H3"].value.endswith("https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final")
    assert ws.cell(7, 1).value == FOOTER == "Not legal advice. CSF 2.0 text © NIST, public domain."
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_api_gap.py tests/test_export.py -k "gap or outcome or scope or starting or workspace_sees" -v`
Expected: FAIL. The gap paths answer 501, `app.export` has no `gap_report`, and `AnswerDetail.parts` is `[]`.

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
from app.db.models import Answer, Item, Questionnaire, Run
from app.runs import create_run
from app.services.capacity import ensure_capacity
from app.settings import get_settings

router = APIRouter(tags=["gap"], responses=ERRORS)


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
    one marked not applicable."""
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
                explanation=(a.text or None) if a and label else None,
                sources=summary(a).sources if a and label else 0,
            )
        )
    return rows


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
    """<the Task 1 docstring, unchanged>"""
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
    """<the Task 1 docstring, unchanged>"""
    ws_id = ws.id
    limit(request, session, "run")
    ensure_capacity(session)
    q = csf.questionnaire_for(session, ws_id, scope)  # commits
    run = latest_run(session, q.id)
    if run is None:
        run = create_run(session, ws_id, q.id, get_settings().models())
    return run_out(session, run)
```

- [ ] **Step 4: Write the parts in the evidence**

In `app/api/answers.py`, add `from app import csf` and import `PartOut` from the schemas and `RunItem` from the models. Replace the dropped loop in `detail` with a helper, and add `_parts`:

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
    """A Checked CSF outcome's parts as the runner stored them (CSF spec 5.2, carry d); [] for anything else."""
    if item.csf_id is None:
        return []
    o = csf.framework().get(item.csf_id)
    stored = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id)) or {}
    )
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

- [ ] **Step 5: Write the gap-report workbook and its endpoint**

In `app/export.py`, add `from app import csf` and import `GapRow` next to `Mapping` from `app.api.schemas` (`uuid`, `Any`, `openpyxl` and `get_column_letter` are already imported). Append:

```python
GAP_SHEET = "Gap report"
GAP_HEAD = (
    "ID", "Function", "Category", "Label", "Explanation", "Quotes", "NIST outcome", "Links", "Related controls",
    "Run date", "CSF version",
)  # CSF spec 7
REVIEW = "Possible gap — review it"
FOOTER = "Not legal advice. CSF 2.0 text © NIST, public domain."
NOT_RUN = "Not run yet"


def _gap_word(r: GapRow) -> str:
    if r.tier == "not_checked":
        return csf.NOT_CHECKED[0].upper() + csf.NOT_CHECKED[1:]  # "Not checked in this version"
    return csf.GAP_WORDS[r.label] if r.label else NOT_RUN


def gap_report(
    rows: list[GapRow],
    citations: dict[uuid.UUID, list[dict[str, Any]]],
    run_date: str,
    version: str,
    controls_url: str,
) -> bytes:
    """The gap-report workbook (CSF spec 7): the review line, a header, one row per outcome in scope (unchecked
    ones too, so coverage is never overstated), then the not-legal-advice footer. NIST's text is verbatim and
    every cell is inert text (`_put`)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = GAP_SHEET
    _put(ws.cell(1, 1), REVIEW)
    for i, title in enumerate(GAP_HEAD, 1):
        _put(ws.cell(2, i), title)
    for n, r in enumerate(rows, 3):
        cited = citations.get(r.answer_id, []) if r.answer_id else []
        quotes = "; ".join(f'"{c["quote"]}" ({c["filename"]} line {c["line_start"]})' for c in cited)
        cells = (
            r.csf_id, r.function, r.category, _gap_word(r), r.explanation, quotes or None, r.outcome,
            f"{r.source_url} {controls_url}", ", ".join(r.related_controls) or None, run_date, version,
        )
        for i, value in enumerate(cells, 1):
            _put(ws.cell(n, i), value)
    _put(ws.cell(len(rows) + 4, 1), FOOTER)
    for i, width in enumerate((10, 10, 28, 20, 60, 60, 60, 40, 20, 12, 10), 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
```

In `app/api/export.py`, import `from app import csf`, `from app.api.gap import gap_rows`, `Answer` from the models and `gap_report` from `app.export`. In `export_run`, right after `q = session.get_one(Questionnaire, run.questionnaire_id)`:

```python
    if q.source == "csf":
        return _gap_report(session, ws.id, run, q)
```

and add:

```python
def _gap_report(session: SessionDep, ws_id: uuid.UUID, run: Run, q: Questionnaire) -> Response:
    """A gap-check run's export (CSF spec 7): the gap-report workbook, named by the scope (a server value)."""
    scope = q.mapping["scope"]
    rows = gap_rows(session, scope, q, run)
    cited = {a.id: a.citations for a in session.scalars(select(Answer).where(Answer.run_id == run.id))}
    body = gap_report(rows, cited, run.started_at.date().isoformat(), q.mapping["csf_version"], csf.CONTROLS_URL)
    audit_log.record(session, ws_id, "export", ref=str(run.id), detail={"rows": len(rows), "scope": scope})
    session.commit()
    return Response(
        body,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="csf-2.0-{scope}-gap-report.xlsx"'},
    )
```

Add one sentence to `export_run`'s docstring: "A gap-check run answers the gap-report workbook instead (CSF spec 7)." Then regenerate `openapi.json` and the types (the docstring is the operation's description).

- [ ] **Step 6: Run the tests, the chain and the eval replays**

Run: `pytest tests/test_api_gap.py tests/test_export.py tests/test_api_runs.py tests/test_openapi.py -v`, then the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`
Expected: PASS, with no eval diff.

- [ ] **Step 7: Commit**

```bash
git add app/csf.py app/api/gap.py app/api/answers.py app/export.py app/api/export.py tests/test_api_gap.py tests/test_export.py openapi.json web/src/lib/api-types.ts
git commit -m "feat(csf): gap check endpoints, per-part evidence and the gap-report sheet" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Check again, Ask-me questions, per-part fills and per-part re-decide

**Lane:** api (after Task 3). **Implementer:** Opus 5.5. **Reviewer:** Opus (lock order, what survives a re-check).

**Files:**
- Modify: `app/runs.py` (`reopen_changed`, `_same_evidence`), `app/api/gap.py` (`start_gap`), `app/questions.py` (`ensure_questions`, `_suggest`, `accept_suggestion`), `app/api/questions.py` (`_suggestion_out`), `app/redecide.py`
- Modify: `tests/test_runs_csf.py`, `tests/test_api_gap.py`, `tests/test_redecide.py`
- Create: `tests/test_questions_csf.py`

**Interfaces:**
- Consumes:
  - from Task 2: `runs.outcome_values`, `csf.part_result`, `csf.part_inputs`, `csf.evidence`, and the stored part shape;
  - from Task 1: `SuggestedFill.part`;
  - existing: `app.interview.recheck` (unchanged, takes keyed `OpenItem`s), `app.redecide.passages_for`.
- Produces:
  - `runs.reopen_changed(session, workspace_id, run_id) -> int` (outcomes re-opened)
  - `runs.REOPEN = ("verified", "partial", "conflict", "unknown")`
  - `questions._opens(session, run_id, item, answer) -> list[OpenItem]`
  - `questions._fill_part(session, sg, answer) -> None`
  - `redecide._redecide_parts(session, workspace_id, answer, parts) -> int`
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


def test_check_again_reruns_only_the_parts_whose_evidence_changed(s: Session) -> None:
    ws, it, run = _done(s)
    _stale(s, run.id, "3")
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # a second press re-opens nothing more
    s.refresh(run)
    ri = _parts_of(s, run.id)
    assert (run.status, ri.state, sorted(ri.parts)) == ("running", "pending", ["1", "2", "4"])
    assert s.scalar(select(Answer).where(Answer.run_id == run.id)) is None
    llm = ByStepLLM({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#3"]


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
def test_check_again_after_an_upload_reopens_only_what_the_new_document_reaches(db: Engine) -> None:
    client, ws_id = visitor(db)
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))  # no documents: every Checked outcome is Gap
    with Session(db) as s:
        _policy(s, ws_id)  # an upload
    llm = ByStepLLM({"stance": YES})
    again = client.post("/api/gap/core/run").json()
    assert (again["id"], again["status"]) == (run["id"], "running")
    _finish(client, run["id"], llm)
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    assert rows["PR.DS-11"]["label"] == "covered"
    assert rows["GV.RM-02"]["label"] == "not_answered"  # Ask me is never re-checked
    calls = len(llm.requests)
    assert 4 <= calls < 73  # only parts the new line reaches
    assert client.post("/api/gap/core/run").json()["status"] == "done"  # nothing changed since
    assert len(llm.requests) == calls
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_runs_csf.py tests/test_api_gap.py -k "check_again" -v`
Expected: FAIL. `runs` has no `reopen_changed`, and the POST on a done run answers it unchanged.

- [ ] **Step 3: Write `reopen_changed` and wire it into the POST**

In `app/runs.py`, add `delete` to the `sqlalchemy` import and `SuggestedFill` to the models import, then:

```python
REOPEN = ("verified", "partial", "conflict", "unknown")  # machine labels; the visitor's own labels stay


def _same_evidence(session: Session, workspace_id: uuid.UUID, o: csf.Outcome, n: int, raw: Mapping[str, Any]) -> bool:
    """A stored part still describes the documents: the deployed wording, and the same passages retrieved now
    (retrieval only, no model call)."""
    if n > len(o.parts) or raw.get("question") != o.parts[n - 1]:
        return False
    found = csf.evidence(session, workspace_id, csf.part_inputs(o)[n - 1])
    return [p.chunk_id for p in found.passages] == raw["chunk_ids"]


def reopen_changed(session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
    """Check again after an upload (CSF spec 5.6, carry c; plan 6B decision 3), with no model call. Every stored
    part of a Checked outcome whose evidence or wording changed is dropped; its outcome goes back to pending,
    with its answer removed and its open fills dismissed, so the step loop re-runs only those parts. An
    outcome the visitor edited, approved, confirmed or marked not applicable stays, and so does a part filled
    by an accepted fill. Locks the run first, so two presses re-open once. Returns the outcomes re-opened;
    with any, the run is running again."""
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id).with_for_update())
    if run is None or run.status != "done":
        session.commit()
        return 0
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
        keep = {
            k: raw
            for k, raw in stored.items()
            if raw.get("statement_id") or _same_evidence(session, workspace_id, o, int(k), raw)
        }
        if len(keep) < len(o.parts):
            reopened[item.id] = keep
    for item_id, keep in reopened.items():  # lock order: answer, then run item, then suggestions
        session.execute(delete(Answer).where(Answer.run_id == run_id, Answer.item_id == item_id))
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id == item_id)
            .values(parts=keep, state="pending", claimed_at=None, attempts=0)
        )
        session.execute(
            update(SuggestedFill)
            .where(SuggestedFill.run_id == run_id, SuggestedFill.item_id == item_id, SuggestedFill.status == "open")
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
        reopen_changed(session, ws_id, run.id)  # commits; nothing changed: it stays done
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
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app import questions as qs
from app.db.models import Item, RunItem, SuggestedFill
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


def test_a_fill_for_one_part_replaces_that_part_and_the_outcome_is_combined_again(s: Session) -> None:
    ws, q, run = _core_done(s)
    # v1's tiers pair no Ask-me outcome with a Checked one by topic (plan 6B note 8): this test pairs one
    s.execute(update(Item).where(Item.questionnaire_id == q.id, Item.csf_id == "GV.RM-02").values(topic="Policy"))
    s.commit()
    question = next(x for x in qs.ensure_questions(s, ws.id, run.id) if _code(s, x.item_ids) == "GV.RM-02")
    reply = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": SAID, "note": "x"}]})
    llm = ByStepLLM({"recheck": reply})
    _, _, found = qs.answer_question(s, ws.id, question.id, SAID, llm, MODELS, TODAY)
    po1, po2 = _item(s, q.id, "GV.PO-01"), _item(s, q.id, "GV.PO-02")
    # one re-check per open part: GV.PO-01's 3 and GV.PO-02's 4, under MAX_RECHECKS
    assert [r.item_id for r in llm.requests] == [f"{po1.id}#{n}" for n in (1, 2, 3)] + [
        f"{po2.id}#{n}" for n in (1, 2, 3, 4)
    ]
    assert sorted((sg.item_id == po1.id, sg.part) for sg in found) == [
        (False, 1), (False, 2), (False, 3), (False, 4), (True, 1), (True, 2), (True, 3)
    ]
    fill = next(sg for sg in found if sg.item_id == po1.id and sg.part == 2)
    a = qs.accept_suggestion(s, ws.id, fill.id)
    assert (a.label, a.value, a.approved_at) == ("partial", "Partial", None)  # Covered + Gap + Gap
    assert a.text.startswith("Evidenced: part 2. No evidence: parts 1, 3.")
    assert a.citations[0]["filename"] == "answer-002.txt"  # the visitor's statement (GV.RM-02 is item 2)
    stored = s.scalars(select(RunItem).where(RunItem.run_id == run.id, RunItem.item_id == po1.id)).one().parts
    assert (stored["2"]["label"], stored["2"]["statement_id"]) == ("verified", str(fill.statement_id))
    states = dict(
        s.execute(select(SuggestedFill.part, SuggestedFill.status).where(SuggestedFill.item_id == po1.id)).tuples()
    )
    assert states == {1: "open", 2: "accepted", 3: "open"}  # only that part's other fills are dismissed
    with pytest.raises(qs.Conflict):
        qs.accept_suggestion(s, ws.id, fill.id)
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
Expected: FAIL. The Checked Gap outcomes are queued as questions, the recheck runs per outcome, and `redecide` turns the outcome into `unknown`.

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

In `_suggest`, replace the `opens = [...]` comprehension with:

```python
    opens = [o for i, a in pairs for o in _opens(session, run_id, i, a)][:MAX_RECHECKS]
```

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

In `app/api/questions.py`, `_suggestion_out` passes `part=s.part`.

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

Run: `pytest tests/test_questions_csf.py tests/test_redecide.py tests/test_questions.py tests/test_runs_csf.py tests/test_api_gap.py -v`, then the backend chain, then `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`
Expected: PASS. The existing interview tests show that a questionnaire's fills (part 0) behave as before.

- [ ] **Step 10: Commit**

```bash
git add app/runs.py app/api/gap.py app/questions.py app/api/questions.py app/redecide.py tests/test_runs_csf.py tests/test_api_gap.py tests/test_redecide.py tests/test_questions_csf.py
git commit -m "feat(csf): check again per changed part, Ask-me questions, per-part fills and re-decide" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The Gap check view (tab 6)

**Lane:** ui, worktree `VART-wt-6b-ui` (no database). **Implementer:** Opus 5.5. **Reviewer:** Opus (design.md, keys, accessibility).

**Files:**
- Create: `web/src/views/GapCheck.tsx`, `web/src/views/GapCheck.test.tsx`
- Modify: `web/src/lib/api.ts`, `web/src/lib/route.ts`, `web/src/lib/route.test.ts`, `web/src/lib/labels.ts`, `web/src/components/ui.tsx`, `web/src/components/Shell.tsx`, `web/src/components/Shell.test.tsx`, `web/src/App.tsx`, `web/src/test/mockApi.ts`, `design.md`

**Interfaces:**
- Consumes:
  - from Task 1 (generated types): `GapOut`, `GapRow`, `PartOut`;
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
        <td className="truncate px-2">{r.label ? <GapChip label={r.label} /> : r.tier === "not_checked" ? "not checked" : ""}</td>
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
  const start = async () => {
    if (!data || busy || running) return;
    setBusy(true);
    setError(null);
    try { await api.startGap(current); reload(); } catch (e) { setError(messageOf(e)); }
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
- add `` | `r` | run the gap check, or check again | Gap check | ``;
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

**Lane:** ui (after Task 5). **Implementer:** Opus 5.5. **Reviewer:** Opus.

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
        <dd>{row.label ? <GapChip label={row.label} /> : tier === "not_checked" ? "not checked in this version" : "not run yet"}</dd>
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
        <ul>
          <QuestionCard q={question} focus={false} onUpdated={(q) => { setQuestion(q); onChanged(); }} onStale={onChanged} />
        </ul>
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

### Task 7: Integration and the Playwright gap flow on recorded replies

**Runs on:** `plan6b`, by the lead (database `vart_test_plan6b`). **Reviewer:** Opus. **Lead-run steps:** the merge, the recording and the cap measurement.

**Files:**
- Create: `web/e2e/gap.spec.ts`
- Modify: `web/e2e/recorded.jsonl` (appended by the record run, never by hand)

**Interfaces:**
- Consumes:
  - everything from Tasks 1-6;
  - `RUN_WAIT` and `xlsxCells` from `web/e2e/helpers.ts`;
  - the Workspace view's `l` (load the sample documents; rules classify all 22, so no model call).
- Produces: one E2E flow. It runs a core gap check over the sample documents, opens a Checked outcome's parts, answers an Ask-me outcome, and checks the exported gap report cell by cell.

- [ ] **Step 1 (lead): Merge the lanes**

On `plan6b`: `git merge --no-ff plan6b-api` then `git merge --no-ff plan6b-ui` (both with the trailer paragraph). Then run `python scripts/export_openapi.py && (cd web && npm run gen:api) && git diff --exit-code openapi.json web/src/lib/api-types.ts`. Run the backend chain, the frontend chain and the eval replays.
Expected: PASS. The two lanes touch disjoint files, so neither merge conflicts. Task 3's docstring change regenerated the types on the api lane; the ui lane built on Task 1's types, which differ only in that description.

- [ ] **Step 2: Write the flow**

`web/e2e/gap.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { RUN_WAIT, xlsxCells } from "./helpers.ts";

// One core gap check (at most 73 stance calls, no draft call) in its own workspace. With the other specs (about
// 150 calls) it stays under the 400-an-hour per-network model-call cap. The Ask-me answer's topic pairs with no
// Checked outcome, so it makes no recheck call.
test("the gap check runs over the sample documents, takes an Ask-me answer and exports the report", async ({ page }) => {
  await page.goto("/?view=workspace");
  await expect(page.getByRole("button", { name: "Load sample documents" })).toBeEnabled();
  await page.keyboard.press("l");
  await expect(page.getByText("access-control-policy.docx")).toBeVisible();
  await page.keyboard.press("6");
  await page.waitForURL(/view=gap/);
  await expect(page.getByText("checked 31 · ask me 5 · not checked 70 · of 106")).toBeVisible();
  await page.keyboard.press("r");
  await expect(page.getByText(/36 of 36 checked · done/)).toBeVisible({ timeout: RUN_WAIT });
  await expect(page.getByRole("row", { name: /^[A-Z]{2}\.[A-Z]{2}-\d\d / })).toHaveCount(106);

  // A Checked outcome: NIST's text and link, and its four parts
  await page.getByRole("row", { name: /^PR\.DS-11 / }).click();
  const drawer = page.getByRole("complementary");
  await expect(drawer.getByText("parts (4)")).toBeVisible();
  await expect(drawer.getByRole("link", { name: "NIST CSF 2.0 reference tool" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // An Ask-me outcome, answered in the inspector
  await page.getByRole("row", { name: /^GV\.RM-02 / }).click();
  await drawer
    .getByLabel("your answer to GV.RM-02")
    .fill("Yes. The board approved a cybersecurity risk appetite statement, and the security team shares it with every new hire.");
  await drawer.getByRole("button", { name: "Send" }).click();
  await expect(drawer.getByText("confirmed by you").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("row", { name: /^GV\.RM-02 / })).toContainText("confirmed by you");

  // The gap report
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const saved = await download;
  expect(saved.suggestedFilename()).toBe("csf-2.0-core-gap-report.xlsx");
  const file = test.info().outputPath(saved.suggestedFilename()); // openpyxl needs the extension
  await saved.saveAs(file);
  const cells = xlsxCells(file, "Gap report", ["A1", "A2", "D2", "A3", "G3", "A110"]);
  expect(cells).toMatchObject({
    A1: "Possible gap — review it",
    A2: "ID",
    D2: "Label",
    A3: "GV.OC-01",
    A110: "Not legal advice. CSF 2.0 text © NIST, public domain.",
  });
  expect(cells.G3).toBe("The organizational mission is understood and informs cybersecurity risk management"); // verbatim
});
```

- [ ] **Step 3: Run it against the recording to verify it fails**

Run: `cd web && LLM_MODE=replay npx playwright test e2e/gap.spec.ts`
Expected: FAIL. The step endpoint answers 500 on a `ReplayMiss`, because no gap-check stance call is recorded yet.

- [ ] **Step 4 (lead): Record the gap flow with the eval key**

Make sure no server is listening on port 8000: Playwright reuses an existing server outside CI, and a replay server would ignore record mode. Then:

```bash
cd web && (set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" LLM_MODE=record npx playwright test e2e/gap.spec.ts)
```

Expected: PASS live in about 13 minutes. `web/e2e/recorded.jsonl` gains at most 73 stance rows, about $0.08 of the eval key; stop and ask Tarun if the key's remaining credit is under $1. Rows already recorded are replayed, not re-paid. The recording appends; the existing rows stay byte for byte (`git diff web/e2e/recorded.jsonl` shows only added lines).

- [ ] **Step 5 (lead): Replay the whole suite twice, measure the cap, scan the recording**

Run: `cd web && LLM_MODE=replay npx playwright test && LLM_MODE=replay npx playwright test`
Expected: PASS both times with no network.

Then read the per-network model calls the last run counted (the e2e server writes to `DATABASE_URL`):

```bash
python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); print(e.connect().execute(text(\"SELECT window_start, hits FROM ip_limits WHERE kind = 'llm' ORDER BY window_start DESC LIMIT 2\")).all())"
```

Expected: the latest window's hits are at most about 225 and under 400. If one suite run straddles an hour, add the two windows. Record the number in Task 8's PROGRESS entry.

Then run `gitleaks dir --redact --no-banner web/e2e/recorded.jsonl` (the `.gitleaks.toml` allowlist covers the 64-hex keys).
Expected: no leaks.

- [ ] **Step 6: Commit**

```bash
git add web/e2e/gap.spec.ts web/e2e/recorded.jsonl
git commit -m "test(e2e): the gap check flow on recorded replies" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Adversary checkpoint 2, docs, final review and the release plan

**Runs on:** `plan6b`, by the lead. **Outward steps:** Tarun's (push, PR, migrate, fast-forward `main`).

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md`, `docs/CONTRACTS.md` (fix-round lines only, if any)

- [ ] **Step 1 (lead): Adversary checkpoint 2**

Dispatch Fable 5.1 on `main..plan6b`: what input, label, lock order, copy or coverage claim did everyone miss? Point it at this plan's Review Focus and at:
- the runner's resume path;
- `reopen_changed` against an accepted fill and an in-flight step;
- the inspector at 375px;
- the export's inert cells;
- the network budget.

Each accepted finding gets a fix by the owning lane's implementer, a reviewer pass, and a CONTRACTS.md change-log line when it touches the contract. Re-run Task 7 Step 5 after any fix that changes what the E2E calls.

- [ ] **Step 2: Write the README section**

In `README.md`, replace the stale status line with `Status: live at https://vart-v2.vercel.app (Plans 1-3, 6).` and append:

```markdown
## Gap check (NIST CSF 2.0)

**What it is.** VART reads your documents against NIST's Cybersecurity Framework 2.0 and reports, outcome by
outcome, what they show: **Covered**, **Partly covered**, **Not met (stated)** when a document says a part is not
done, **Documents disagree**, or **Gap** when nothing speaks to it. Each checked outcome is cut into NIST's own
parts; every part is asked as a question through the same engine that fills questionnaires, and code combines
the parts' labels and writes the explanation. Every finding quotes your line next to NIST's verbatim text and
links to NIST, with the related SP 800-53 Rev 5 controls. The report exports as a gap-report sheet.

**What it is not.** It is not legal advice, an audit, a certification or a compliance score, and no overall score
is shown. Every finding reads "possible gap, review it". It checks 31 of CSF 2.0's 106 outcomes against documents,
asks you about 5 governance outcomes that documents rarely state, and lists the other 70 as not checked in this
version. A checked outcome is judged on documents only: your answers confirm the Ask-me outcomes and can fill a
checked part only as a suggestion you accept. On the dev pack its outcome labels agree with a blind judge's key
22 times in 31 (0.71 against a 0.80 target, reported in `evals/results/gap-dev.md`).

Not legal advice. CSF 2.0 text © NIST, public domain.
```

- [ ] **Step 3: Update `CLAUDE.md` and the CSF spec**

`CLAUDE.md` Map:
- add `app/api/gap.py` (gap-check endpoints) to the API line;
- in the UI line, add `GapCheck.tsx` and `GapDrawer.tsx` (the Gap check view and its inspector) after `web/src/views/`;
- in the Engine line, after `app/csf.py ...`, add "; `app/runs.py` answers a gap-check run part by part (`run_items.parts`)".

Commands: the E2E line gains "`gap.spec.ts` records alone (`LLM_MODE=record npx playwright test e2e/gap.spec.ts`)".

The CSF spec:
- under 5.6's last bullet add `Sync (Plan 6B): a check again re-runs only the parts whose evidence or wording changed since they were judged (retrieval only, no model call); an unchanged part sends the same prompt, so its result cannot change. The visitor starts it with r; an upload starts no model call by itself.`;
- under section 7 add `Sync (Plan 6B): the path's first segment is "workspace" (the API has no company name); the filter toggles have no single keys; the coverage line sits in the status line; 800-53 controls link to NIST's SP 800-53 Rev 5 page.`;
- add a change-log line `2026-10-06: Plan 6B sync, no new behaviour beyond 5.6's narrowing (sections 5.6 and 7).`

- [ ] **Step 4: Update `docs/PROGRESS.md`**

- At a glance: the 6A row reads `done, live`. Add a row `| 6B CSF gap check, the visitor half | done on plan6b; release pending | Gap check view (tab 6), per-part runner and resume, check again per changed part, Ask-me answers, gap-report sheet, one E2E flow (<N> model calls per full suite) |`.
- Decisions, dated the merge day, from this plan's execution notes:
  - the per-part migration (two columns, no table);
  - check again re-runs only changed parts, started by `r`, never by an upload;
  - a gap-check run's export is the gap report;
  - controls link to one NIST page;
  - the sample pack stays without the gap extension;
  - per-part fills are built but unpaired by v1's tiers;
  - the filter toggles have no keys.
- "6B carry-over": mark (a), (b), (c) and (d) done, each with its task. Keep "Stance improvement" and "`app.csf.evidence` drops statements after the top-8 cut" as carried to a later plan. The latter still holds, and `reopen_changed` inherits it: a new Ask-me statement that reaches a part's top 8 changes that part's passages and re-runs it once.
- Add `### Plan 6B`, `_Filled in after the release (Step 8)._` under Releases.

- [ ] **Step 5: Run every chain once more and commit**

Run: the backend chain, the frontend chain, `python -m evals.run --pack dev && python -m evals.run --pack gap-dev && git diff --exit-code evals/results`, and `cd web && LLM_MODE=replay npx playwright test`.
Expected: PASS.

```bash
git add README.md CLAUDE.md docs/PROGRESS.md docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md docs/CONTRACTS.md
git commit -m "docs(csf): Plan 6B readme section, map, spec sync and progress" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6 (lead): Final Opus review**

An Opus reviewer reads `main..plan6b` against this plan, the CSF spec sections 5, 7 and 11, and the Review Focus. Fix rounds follow its findings; then re-run Step 5's chains.

- [ ] **Step 7 (lead → Tarun): The release plan**

Send Tarun this plan. Every step is his; the lead runs nothing outward.
1. Push `plan6b` and open a pull request to `main`.
2. Wait for green CI: gates, backend, frontend, e2e.
3. From the branch head, run `ops/setup.sh migrate`: Neon goes `a7c3e9d1b2f4` → `c4e8a2d6f1b3` before `main` moves, because Vercel deploys `main` at once. The migration is additive, and the live code ignores both columns.
4. Fast-forward `main` to `plan6b` and push. Vercel deploys.
5. Check that the smoke test passes, `/api/health` reads `"status":"ok"`, and the Gap check tab opens on https://vart-v2.vercel.app.

No new file ships in the function bundle (`data/csf/csf-2.0.json` shipped with 6A), so no preview bundle check is needed.

- [ ] **Step 8 (lead): The release record**

After Tarun's step 5, fill `### Plan 6B` in `docs/PROGRESS.md`:
- `main` = `<sha>`, merged by PR `#<n>` after green CI;
- the migration;
- the smoke and health results;
- the E2E's model calls per suite.

Commit it on `plan6b-record` from the new `main`, with the trailer. Pushing it is Tarun's.

---

## Self-review notes (for the lead)

- **Spec coverage.**
  - 5.1 (start a run per scope, the same run machinery, caps and expiry): Task 3 `start_gap`, through `create_run`, `limit("run")`, `ensure_capacity` and the existing step endpoint.
  - 5.2-5.3 (part by part, labels combined by code): Task 2.
  - 5.4 (Ask-me redacted, stored, Confirmed by you, Not answered): Task 2 `ASK`, Task 4 `ensure_questions` and `test_an_ask_me_answer_is_redacted_stored_and_confirmed`, Task 3 `gap_rows`, Task 6 answer box.
  - 5.5 (not checked: no call, no label): Task 3 view test, Task 5 rows.
  - 5.6 (per-part re-check, accepted fill replaces one part before combine): Task 4.
  - 5.7 (claim by parts at most 8, resume after a refusal, spend before every call, no open transaction): Task 2.
  - 6 (no schema change beyond the one migration): Task 1.
  - 7 (tab 6, path, scope keys, r, e, filter counts, grouped 28px rows, inspector with NIST text, link, controls, explanation, footnoted sources, line listings, dropped evidence, Ask-me box, status line, export columns, copy): Tasks 3, 5 and 6.
  - 8 (the E2E side): Task 7.
  - 11 (view, export, README): Tasks 3-8.
  - Carries (a)-(d): Tasks 2, 2, 4 and 3+6. Ruling 5 (csf questionnaires not counted, listed or deleted) was already in Plan 3's code; Task 3 pins listing.
- **Placeholders.** Two kinds of text stand in for content that already exists:
  - "<keep the existing docstring>" (Task 2 `check_parts`) and "<the Task 1 docstring, unchanged>" (Task 3) name text written earlier, in Task 1 or in 6A, not left to write;
  - `<N>`, `<sha>` and `<n>` in Task 8 are numbers only the run and the release produce.
- **Type consistency.**
  - `check_part(session, workspace_id, o, n, llm, models, spend)` is the same in Tasks 2-4.
  - `part_result(o, n, raw)` and `outcome_values(o, parts)` (parts keyed `"1"`..`"n"`) are the same in Tasks 2, 3 (`_parts`), 4 (`_fill_part`, `_redecide_parts`).
  - `reopen_changed(session, workspace_id, run_id) -> int` is the same in Task 4 and CONTRACTS.md.
  - `gap_rows(session, scope, q, run)` is used by `gap_view` and `_gap_report`.
  - `gap_report(rows, citations, run_date, version, controls_url)` is the same in its test and its endpoint.
  - On the frontend, `GapRow`, `GapOut`, `PartOut`, `GapLabel`, `GapScope` come from the generated types.
  - `GapChip` takes `GapLabel`, and `PartOut.label` (a `PartLabel`) is assignable to it.
  - `useStepLoop(runId, data, onData, onGone)` is called with a `RunRowsOut` made from `GapOut.run`.
- **Counts that tests pin:** 106 outcomes, 31 / 5 / 70 tiers, 36 items in the core run, 73 parts, Recover's one in-scope outcome (RC.RP-01), PR.DS-11's four parts, the first core step taking GV.OC-03, GV.RM-02, GV.RR-02 and GV.PO-01 (1 + 1 + 1 + 3), and the gap report's footer at row 110 for the core. A tier change moves them together (6A self-review).
- **Review Focus.** Each of the five lines has its test in the owning task. Two failure modes outside the five are noted and accepted:
  - two steps on one stale claim (Plan 4 carry N1) could store one part twice; the later write wins and nothing is charged twice beyond what the existing N1 allows;
  - a withdrawn NIST id in an old run ends at `MAX_ATTEMPTS` (the `ponytail:` comment in `_answer_outcome`).
