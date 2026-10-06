# VART - Plan 6A: CSF 2.0 gap check, backend and evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the existing engine at NIST's Cybersecurity Framework 2.0: a committed, drift-tested copy of NIST's outcomes; a built-in CSF questionnaire per workspace and scope; gap labels as a pure display mapping over decide's output; Ask-me outcomes answered through the interview queue and `store_statement`; and a `gap-dev` eval pack with a code-derived key and fail-closed gates, replayed in CI.

**Architecture:** `datakit/csf.py` turns NIST's CSF 2.0 Reference Tool export into a trimmed, committed extract (NIST's fields only) and builds `data/csf/csf-2.0.json` from it plus `data/csf/tiers.yaml` (VART's tier and question per outcome); a drift check compares the two. `app/csf.py` loads that file, creates or reuses the workspace's built-in questionnaire (`questionnaires.source = 'csf'`, one migration), runs a Checked outcome through `answer_item` unchanged, never calls a model for an Ask-me or not-checked outcome, and maps decide's label to the gap label. `datakit/gap.py` adds a gap-only extension to the dev fact sheet (one new document, two controls, three statements, four traps, the outcome-to-control map) and derives the key with `derive_key`'s rules; `evals/gap.py` runs and scores the `gap-dev` pack, reached through `python -m evals.run --pack gap-dev`.

**Tech Stack:** Python 3.12, SQLAlchemy 2 + Alembic, openpyxl (the NIST export), pydantic (datakit schemas), the existing record/replay LLM client, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md` sections 4 (data), 5 (run flow), 6 (data model), 8 (evals) and 9 (security), on top of the main spec `docs/superpowers/specs/2026-10-03-vart-v2-design.md` (6.7 decide, 6.9 interview, 6.11 database, 8 evals, 9 security). **Out of scope, deferred to Plan 6B** (written after Plan 3 freezes the HTTP contract): spec section 7 (the Gap check view, its keys and filter line, the inspector drawer, the status line, the xlsx gap-report sheet and the copy), the README section, the Playwright E2E test, and the HTTP wiring (the run and step endpoints for a CSF run, the per-run and per-IP caps on it, the questions API for Ask-me answers, and the re-check after a new upload). 6A delivers the library functions 6B and Plan 3's step runner call; it adds no endpoint.

## Execution notes (read first)

- **Starts after Plan 2's release**, when `main` holds Plan 2 (engine, ingest, evals, `evals/results/latest.*` and the dev eval in CI; plan2c Task 6). It does not need Plan 3. Worktree `~/Desktop/portfolio/projects/VART-wt-csf`; the lead creates branch `plan6a` there from `main` and merges `spec-csf-gap` (the spec and this plan) into it first. Database `vart_test_csf` for agents, `vart_test_record` for the lead's recording run.
- **The tier IDs below were read from the real NIST export** (downloaded while planning, 2026-10-05: 185 subcategory rows, 79 withdrawn, 106 active). Task 1 downloads it again; if NIST's file changed in between, the drift test and the counts say so and the lead re-checks the lists with Tarun.
- **Why a gap extension (spec section 8: "no new documents unless an outcome needs one").** The dev pack states no outcome-level negative that the CSF wording turns into "Not met", and its two questionnaire disagreements (X1 restore tests quarterly vs annually, X2 logs kept one year vs 90 days) are not contradictions under the CSF outcomes' wording ("backups are tested", "logs are generated"). So 6A adds one document, `security-improvement-plan.md`, with three planned-only sentences (two stated non-compliances and one disagreement with the logging policy). It lives in `data/dev/gap/`, loaded only by the `gap-dev` pack: the questionnaire keys, the dev eval, its recordings and its baseline do not change. Whether the production sample pack gains the document is 6B's call.
- **Decisions this plan proposes; Tarun confirms them at Task 1's review gate:**
  1. The Checked tier (29 outcomes) includes three Identify outcomes outside spec 4's "asset management basics": ID.RA-01 (vulnerabilities identified), ID.RA-02 (threat intelligence received, a planted Not met) and ID.RA-08 (vulnerability disclosure).
  2. `related_controls` keeps NIST's SP 800-53 **Rev 5.2.0** references (the export also lists Rev 5.1.1, which differs on a few outcomes). Some references name a whole family (`PT`, `CP`, `IR`); the identifier check accepts a family, a control (`AC-02`) and an enhancement (`CP-02(08)`).
  3. `source_url` is the CSF 2.0 Reference Tool page for every outcome: no per-outcome NIST page could be verified while planning (the tool's deep links are single-page-app routes). 6B may switch to a per-outcome link after a browser check; the drift test then compares the new value.
  4. `csf_version`, `retrieved` and `source` are stored once at the top of the file, not repeated in each entry (spec 4 lists them as entry fields).
  5. Labels the spec table leaves open: `na` (Not applicable) shows no gap label; a Checked outcome the visitor confirmed (`user_confirmed` with a statement) shows Confirmed by you, like an Ask-me one.
  6. Questions for you holds the Ask-me outcomes only; Checked findings (Gap, Documents disagree) are not queued (spec 5 is silent; 6B may add them).

## Global Constraints

- Every commit message ends with exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never open, list, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/`; never type the sponsor's company or people names.
- Backend chain, green before every commit: `ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check && python -m datakit.validate all` (with `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_csf && export DATABASE_URL=$TEST_DATABASE_URL`). Never run `docker compose` from a worktree.
- Tests never touch the network or a real key (pytest-socket); model calls go through `tests/fakes.py`'s `FakeLLM`. The NIST download (Task 1) and the recording run (Task 7) are lead-run commands, never tests.
- "The app never fetches it." (CSF spec 4) `data/csf/csf-2.0.json` is read from disk; nothing in it is executed (CSF spec 9).
- "What the visitor sees as 'the framework' is always NIST's verbatim `outcome` text. Only `question` and `tier` are VART's." (CSF spec 4)
- "Refreshing the file is a deliberate change with a new `retrieved` date, a re-run of the eval and a change-log line." (CSF spec 4) The change log is the comment block at the top of `data/csf/tiers.yaml`.
- Decide does not change (CSF spec 5.3): gap labels are computed from `Decision.label` and `Decision.value` only. `app/decide.py`, `app/text.py`, `app/patterns.py`, `app/contracts.py` and the signatures in `docs/CONTRACTS.md` are not edited by any task; no frozen signature needs to change. Adding a new row for `app/csf.py` to `docs/CONTRACTS.md` (Task 7) needs the lead's OK and a change-log line (CLAUDE.md rule 10).
- Engine code spends the budget before every model call and holds no database transaction across one (CLAUDE.md rule 11): `check_outcome` reaches a model only through `answer_item`, which already does both; Ask-me and not-checked outcomes make no model call (CSF spec 5.4-5.5).
- `ck_answers_cited` is unchanged: no Covered or Partly covered result without a citation (CSF spec 6).
- "Uploads and Ask-me answers are redacted before any model call" (CSF spec 9): Ask-me answers go through `store_statement`, which redacts like an upload.
- "Every gate fails closed when it has nothing to measure. CI replays recorded model outputs; recording uses the capped eval key." (CSF spec 8) Gates tighten after the first baseline to max(spec value, baseline - 0.02).
- Calls with an OpenRouter key use only the eval key (`VART_EVAL_OPENROUTER_API_KEY` in `~/.config/vart/eval.env`), loaded inside the command and never printed; the lead runs them without asking Tarun and asks before spending past the key's $5 cap.
- Tuning rules (CSF spec 10): "phrasings are tuned within the plan's tuning rules, never per document". The key is never edited to match the engine; a fact-sheet correction is allowed only when a document really says something the sheet did not register.
- Each task owns the files it lists. The same failure twice: stop and report. Never weaken, skip or delete a test.

## Review Focus

1. **The tier list changes after a workspace already made its CSF questionnaire** (a deploy that moves an outcome into Checked, or rewords a question). Expect: the next run gets a new questionnaire with the new items, never the stale ones. Pinned in Task 4 (`test_a_changed_tier_list_gives_a_new_questionnaire`).
2. **NIST's export changes shape on a refresh** (a new withdrawn row, references under a new revision label, categories listed in another order). Expect: names are looked up by code, withdrawn rows are skipped, an export with no Rev 5.2.0 reference is refused with a readable error, and the drift check names each outcome and field that differs. Pinned in Task 1.
3. **An Ask-me or not-checked outcome reaches the runner** (6B's step loop treats every item alike). Expect: no retrieval and no model call for Ask-me; a `ValueError` for not-checked. Pinned in Task 4 (`test_ask_me_and_not_checked_outcomes_never_reach_a_model`).
4. **Coverage overstated**: a not-checked outcome or an unanswered Ask-me outcome shown with a label, or "Confirmed by you" without a stored statement. Expect: no label, Not answered, and the `honest_tiers` gate failing otherwise. Pinned in Task 3 (`test_ask_me_is_confirmed_only_with_a_stored_statement`, `test_not_checked_outcomes_never_carry_a_label`) and Task 6 (`test_an_ask_me_label_without_a_statement_fails_honest_tiers`).
5. **Replaying `gap-dev` on CI** after the judge or classify default changes. Expect: byte-identical `evals/results/gap-dev.{json,md}` (the report names only the stance and draft models, the only ones the pack calls), and `evals/results/latest.*` untouched by a gap-dev run. Pinned in Task 6 (`test_run_answers_checked_outcomes_stores_ask_answers_and_deletes_its_workspace`, `test_main_writes_the_gap_pack_to_its_own_results_files`).

## Review gates (run by the lead)

- Reviewers: Opus for Task 2 (migration), Task 5 (key derivation) and Task 6 (eval gates); Sonnet for Tasks 1, 3 and 4.
- **Tarun's review gate** in Task 1 Step 7: the exact Checked and Ask-me IDs and their questions, before any key is derived.
- **Adversary checkpoint (Fable 5.1)** on `main..plan6a` after Task 6, before Task 7's recording run: what input, label or gate did everyone miss? Its fixes land before anything is recorded, so nothing is recorded twice.
- Final Opus review of the whole branch after Task 7, before the branch is pushed. Pushing and the pull request need Tarun's OK.

## File Structure

```
datakit/csf.py                                   NEW (Task 1)   NIST export -> extract; extract + tiers -> csf-2.0.json; drift check
data/csf/source/csf-2.0-extract.json             NEW (Task 1)   NIST's fields only, verbatim (written by datakit.csf extract)
data/csf/tiers.yaml                              NEW (Task 1)   VART's part: tier and question per outcome, change log
data/csf/csf-2.0.json                            NEW (Task 1)   the file the app reads (written by datakit.csf build)
datakit/validate.py                              MODIFY (Tasks 1, 5)  stages "csf" and "gap"; planned_only trap rule
data/NOTICE.md                                   MODIFY (Task 1)
tests/datakit/test_csf.py                        NEW (Task 1)
migrations/versions/a7c3e9d1b2f4_questionnaires_csf_source.py   NEW (Task 2)
app/db/models.py, tests/test_models.py           MODIFY (Task 2)
app/csf.py                                       NEW (Task 3), MODIFY (Task 4)
.vercelignore                                    MODIFY (Task 3)   ship data/csf/csf-2.0.json with the function
tests/test_csf.py                                NEW (Task 3), MODIFY (Task 4)
datakit/schemas.py                               MODIFY (Task 5)   GapOutcome, GapFacts, TrapKind planned_only
datakit/gap.py                                   NEW (Task 5)
data/dev/gap/facts.yaml, data/dev/gap/docs/security-improvement-plan.md   NEW (Task 5)
data/dev/key/csf-core.yaml                       NEW (Task 5, written by datakit.gap)
tests/datakit/test_gap.py                        NEW (Task 5)
evals/gap.py, evals/fixtures/gap-dev-answers.json, tests/test_eval_gap.py   NEW (Task 6)
evals/run.py, evals/score.py                     MODIFY (Task 6)   pack dispatch; gates() takes a table
evals/recorded/gap-dev.jsonl, evals/results/gap-dev.{json,md}            NEW (Task 7, written by the record run)
.github/workflows/ci.yml, CLAUDE.md, docs/PROGRESS.md, docs/CONTRACTS.md, the CSF spec   MODIFY (Task 7)
```

---

### Task 1: NIST's CSF 2.0 data, the tiers, and the drift check

**Reviewer:** Sonnet. **Lead-run step:** Step 3 (network). **Tarun's gate:** Step 7.

**Files:**
- Create: `datakit/csf.py`, `data/csf/tiers.yaml`, `tests/datakit/test_csf.py`
- Create (written by commands): `data/csf/source/csf-2.0-extract.json`, `data/csf/csf-2.0.json`
- Modify: `datakit/validate.py` (stage `csf`), `data/NOTICE.md`

**Interfaces:**
- Consumes: `datakit.schemas.load_yaml_raw`; openpyxl.
- Produces: `datakit.csf.extract(path: Path) -> list[dict[str, Any]]`; `extract_file(path: Path, retrieved: str) -> dict[str, Any]`; `build(nist: dict[str, Any], tiers: dict[str, Any]) -> dict[str, Any]`; `problems(nist, tiers, built) -> list[str]`; `check() -> list[str]`; `main(argv) -> int`; constants `EXTRACT`, `TIERS`, `BUILT`, `DOWNLOAD_URL`, `TOOL_URL`, `OUTCOMES = 106`, `CONTROL`. The built file's shape, which `app/csf.py` (Task 3) reads: `{"csf_version": "2.0", "retrieved": "YYYY-MM-DD", "source": DOWNLOAD_URL, "outcomes": [{"id", "function", "category", "outcome", "related_controls": [...], "source_url", "tier": "checked"|"ask"|"not_checked", "question": str|null}]}`, in NIST's order. Validate stage `csf`.

The source, verified while planning (2026-10-05): NIST's informative-references page (`https://www.nist.gov/cyberframework/informative-references`) links "all informative references" to `https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all`, which returns a 141 KB xlsx from the CSF 2.0 Reference Tool with sheets `Introduction` and `CSF 2.0`. The `CSF 2.0` sheet: row 1 a title, row 2 the headers `Function | Category | Subcategory | Implementation Examples | Informative References`, then one row per function (`GOVERN (GV): ...`), category (`Organizational Context (GV.OC): ...`) and subcategory (`GV.OC-01: The organizational mission is ...`); withdrawn ones read `ID.AM-06: [Withdrawn: Incorporated into GV.RR-02, GV.SC-02]`; references are newline-separated `Source: ID` lines such as `SP 800-53 Rev 5.2.0: AC-02`. The xlsx itself is not committed: its other references (ISO/IEC 27001, PCI DSS, CCM and others) are not NIST's to give, so only NIST's columns are kept.

- [ ] **Step 1: Write the failing tests**

`tests/datakit/test_csf.py`:

```python
import json
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from datakit import csf
from datakit.schemas import load_yaml_raw
from datakit.validate import STAGES


def _committed() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        json.loads(csf.EXTRACT.read_text(encoding="utf-8")),
        load_yaml_raw(csf.TIERS),
        json.loads(csf.BUILT.read_text(encoding="utf-8")),
    )


def _workbook(path: Path, rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CSF 2.0"
    ws.append([None, "The NIST Cybersecurity Framework 2.0"])
    ws.append(["Function", "Category", "Subcategory", "Implementation Examples", "Informative References"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_the_committed_data_matches_nists_extract() -> None:
    assert csf.check() == []
    assert STAGES["csf"]("dev") == []


def test_all_106_outcomes_are_kept_in_nists_order_with_the_proposed_tiers() -> None:
    nist, _, built = _committed()
    ids = [o["id"] for o in built["outcomes"]]
    assert ids == [o["id"] for o in nist["outcomes"]] and len(ids) == csf.OUTCOMES
    assert {o["function"] for o in built["outcomes"]} == {
        "Govern", "Identify", "Protect", "Detect", "Respond", "Recover"
    }
    assert Counter(o["tier"] for o in built["outcomes"]) == {"checked": 29, "ask": 5, "not_checked": 72}
    assert built["csf_version"] == "2.0" and built["source"] == csf.DOWNLOAD_URL


def test_a_changed_nist_field_is_named_with_its_outcome() -> None:
    nist, tiers, built = _committed()
    built["outcomes"][0]["outcome"] += " (edited)"
    first = built["outcomes"][0]["id"]
    assert csf.problems(nist, tiers, built) == [f"{first}: outcome differs from NIST's extract"]


def test_an_outcome_missing_from_the_built_file_is_named() -> None:
    nist, tiers, built = _committed()
    gone = built["outcomes"].pop()["id"]
    assert f"{gone}: missing from csf-2.0.json" in csf.problems(nist, tiers, built)


def test_a_control_that_is_not_an_sp_800_53_identifier_is_named() -> None:
    nist, tiers, built = _committed()
    nist["outcomes"][0]["related_controls"].append("AC-2")
    first = nist["outcomes"][0]["id"]
    assert f"{first}: AC-2 is not an SP 800-53 rev5 identifier" in csf.problems(nist, tiers, built)


@pytest.mark.parametrize("control", ["AC-02", "CP-02(08)", "PT", "SA-15(13)"])
def test_controls_enhancements_and_families_are_identifiers(control: str) -> None:
    assert csf.CONTROL.fullmatch(control)


@pytest.mark.parametrize("control", ["AC-2", "ac-02", "AC-02(8)", "AC-02 ", "A.5.15"])
def test_other_strings_are_not_identifiers(control: str) -> None:
    assert not csf.CONTROL.fullmatch(control)


def test_tiers_name_real_outcomes_once_with_ascii_questions() -> None:
    nist, tiers, built = _committed()
    first_checked = next(iter(tiers["checked"]))
    tiers["ask"]["XX.YY-01"] = "Is it done?"
    tiers["ask"][first_checked] = "Is it done?"
    tiers["checked"][first_checked] = "Is it done"
    found = csf.problems(nist, tiers, built)
    assert "ask XX.YY-01: not a CSF 2.0 outcome" in found
    assert f"{first_checked}: in both checked and ask" in found
    assert f"checked {first_checked}: the question must be ASCII and end with '?'" in found


def test_extract_reads_nists_layout_and_skips_withdrawn_rows(tmp_path: Path) -> None:
    path = tmp_path / "csf.xlsx"
    refs = "\n".join(
        [
            "ISO/IEC 27001:2022: A.5.15",
            "SP 800-53 Rev 5.1.1: AC-01",
            "SP 800-53 Rev 5.2.0: AC-01",
            "SP 800-53 Rev 5.2.0: AC-02(01)",
            "SP 800-53 Rev 5.2.0: AC-01",
        ]
    )
    _workbook(
        path,
        [
            ["PROTECT (PR): Safeguards to manage the organization's cybersecurity risks are used", None, None],
            [None, "Identity Management, Authentication and Access Control (PR.AC): [Withdrawn: Moved to PR.AA]"],
            [None, "Identity Management, Authentication, and Access Control (PR.AA): Access is limited"],
            [None, None, "PR.AA-05: Access permissions are defined in a policy and reviewed ", "Ex1: x", refs],
            [None, None, "PR.AA-07: [Withdrawn: Incorporated into PR.AA-05]", None, None],
        ],
    )
    assert csf.extract(path) == [
        {
            "id": "PR.AA-05",
            "function": "Protect",
            "category": "Identity Management, Authentication, and Access Control",
            "outcome": "Access permissions are defined in a policy and reviewed",
            "related_controls": ["AC-01", "AC-02(01)"],
        }
    ]


def test_extract_refuses_an_export_without_sp_800_53_references(tmp_path: Path) -> None:
    path = tmp_path / "csf.xlsx"
    _workbook(
        path,
        [
            ["PROTECT (PR): Safeguards are used"],
            [None, "Data Security (PR.DS): Data are managed"],
            [None, None, "PR.DS-01: Data-at-rest is protected", None, "SP 800-53 Rev 6.0: SC-28"],
        ],
    )
    with pytest.raises(ValueError, match="SP 800-53 Rev 5.2.0"):
        csf.extract(path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/datakit/test_csf.py -q`
Expected: FAIL, `ImportError: cannot import name 'csf' from 'datakit'`.

- [ ] **Step 3: Write `datakit/csf.py`**

```python
"""NIST CSF 2.0 reference data for the gap check (CSF spec 4). NIST's part (ids, function and category names,
outcome text, SP 800-53 Rev 5.2.0 references) comes only from the committed extract of NIST's CSF 2.0 Reference
Tool export; VART's part (tier, question) only from data/csf/tiers.yaml. The app reads the built file and never
fetches anything.

    python -m datakit.csf extract DOWNLOAD.xlsx --retrieved YYYY-MM-DD   # the lead, once per NIST refresh
    python -m datakit.csf build                                         # writes data/csf/csf-2.0.json
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

from datakit.schemas import load_yaml_raw

ROOT = Path(__file__).resolve().parent.parent
CSF = ROOT / "data" / "csf"
EXTRACT = CSF / "source" / "csf-2.0-extract.json"
TIERS = CSF / "tiers.yaml"
BUILT = CSF / "csf-2.0.json"
DOWNLOAD_URL = "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all"
TOOL_URL = "https://csrc.nist.gov/projects/cybersecurity-framework/filters#/csf/filters"
SHEET = "CSF 2.0"
REFERENCE = "SP 800-53 Rev 5.2.0: "
OUTCOMES = 106
# A control (AC-02), an enhancement (CP-02(08)) or, where NIST maps a whole family, the family (PT).
CONTROL = re.compile(r"[A-Z]{2}(?:-\d{2}(?:\(\d{2}\))?)?")
_CODE = re.compile(r"\(([A-Z]{2}(?:\.[A-Z]{2})?)\)")
_OUTCOME = re.compile(r"([A-Z]{2}\.[A-Z]{2}-\d{2}): (.+)", re.DOTALL)
NIST_FIELDS = ("id", "function", "category", "outcome", "related_controls", "source_url")


def extract(path: Path) -> list[dict[str, Any]]:
    """One entry per active outcome, in NIST's order. Function and category names are read from their own rows
    ("PROTECT (PR): ...", "Data Security (PR.DS): ...") and looked up by code, so row order does not matter;
    withdrawn rows are skipped."""
    sheet = openpyxl.load_workbook(path, read_only=True)[SHEET]
    rows = [tuple(r) + (None,) * 5 for r in sheet.iter_rows(min_row=3, values_only=True)]
    names: dict[str, str] = {}
    for row in rows:
        for cell in row[:2]:
            if isinstance(cell, str) and "[Withdrawn" not in cell and (m := _CODE.search(cell)):
                names[m.group(1)] = cell[: m.start()].strip()
    out: list[dict[str, Any]] = []
    for row in rows:
        cell, refs = row[2], row[4]
        if not isinstance(cell, str) or "[Withdrawn" in cell or not (m := _OUTCOME.fullmatch(cell.strip())):
            continue
        csf_id = m.group(1)
        controls = [x[len(REFERENCE) :].strip() for x in str(refs or "").splitlines() if x.startswith(REFERENCE)]
        out.append(
            {
                "id": csf_id,
                "function": names[csf_id[:2]].title(),
                "category": names[csf_id.split("-")[0]],
                "outcome": m.group(2).strip(),
                "related_controls": list(dict.fromkeys(controls)),
            }
        )
    if not any(o["related_controls"] for o in out):
        raise ValueError(f"{path.name}: no outcome has a '{REFERENCE.strip()}' reference; did NIST change the export?")
    return out


def extract_file(path: Path, retrieved: str) -> dict[str, Any]:
    return {
        "source": DOWNLOAD_URL,
        "retrieved": retrieved,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "csf_version": "2.0",
        "outcomes": extract(path),
    }


def _tier(tiers: dict[str, Any], csf_id: str) -> str:
    return next((t for t in ("checked", "ask") if csf_id in (tiers.get(t) or {})), "not_checked")


def build(nist: dict[str, Any], tiers: dict[str, Any]) -> dict[str, Any]:
    def entry(o: dict[str, Any]) -> dict[str, Any]:
        tier = _tier(tiers, o["id"])
        question = (tiers.get(tier) or {}).get(o["id"]) if tier != "not_checked" else None
        return {**o, "source_url": TOOL_URL, "tier": tier, "question": question}

    return {
        "csf_version": nist["csf_version"],
        "retrieved": nist["retrieved"],
        "source": nist["source"],
        "outcomes": [entry(o) for o in nist["outcomes"]],
    }


def problems(nist: dict[str, Any], tiers: dict[str, Any], built: dict[str, Any]) -> list[str]:
    """The drift check (CSF spec 4): NIST's fields in the built file equal the extract, every control is an
    SP 800-53 rev5 identifier, the tiers name real outcomes once, and the built file is not stale."""
    p: list[str] = []
    ids = [o["id"] for o in nist["outcomes"]]
    if len(ids) != OUTCOMES:
        p.append(f"{len(ids)} outcomes in NIST's extract, expected {OUTCOMES}")
    p += [f"duplicate outcome {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for o in nist["outcomes"]:
        p += [
            f"{o['id']}: {c} is not an SP 800-53 rev5 identifier"
            for c in o["related_controls"]
            if not CONTROL.fullmatch(c)
        ]
    checked, ask = tiers.get("checked") or {}, tiers.get("ask") or {}
    for tier, questions in (("checked", checked), ("ask", ask)):
        p += [f"{tier} {i}: not a CSF 2.0 outcome" for i in questions if i not in ids]
        p += [
            f"{tier} {i}: the question must be ASCII and end with '?'"
            for i, q in questions.items()
            if not (isinstance(q, str) and q.isascii() and q.rstrip().endswith("?"))
        ]
    p += [f"{i}: in both checked and ask" for i in sorted(set(checked) & set(ask))]
    want = build(nist, tiers)
    have = {o["id"]: o for o in built.get("outcomes", [])}
    for o in want["outcomes"]:
        h = have.get(o["id"])
        if h is None:
            p.append(f"{o['id']}: missing from csf-2.0.json")
            continue
        p += [f"{o['id']}: {k} differs from NIST's extract" for k in NIST_FIELDS if h.get(k) != o[k]]
    p += [f"{i}: not in NIST's extract" for i in have if i not in ids]
    if not p and built != want:
        p.append("csf-2.0.json is stale: run python -m datakit.csf build")
    return p


def load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    built = json.loads(BUILT.read_text(encoding="utf-8")) if BUILT.exists() else {}
    return json.loads(EXTRACT.read_text(encoding="utf-8")), load_yaml_raw(TIERS), built


def check() -> list[str]:
    return problems(*load())


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("xlsx", type=Path)
    ex.add_argument("--retrieved", required=True, type=date.fromisoformat)
    sub.add_parser("build")
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        _write(EXTRACT, extract_file(args.xlsx, args.retrieved.isoformat()))
        print(f"wrote {EXTRACT.relative_to(ROOT)}")
        return 0
    nist, tiers, _ = load()
    _write(BUILT, build(nist, tiers))
    found = check()
    for x in found:
        print(x, file=sys.stderr)
    print(f"wrote {BUILT.relative_to(ROOT)}: {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4 (lead, network): Download NIST's export and write the extract**

Run by the lead, in its own terminal; it is the only step in this plan that downloads anything:

```bash
cd ~/Desktop/portfolio/projects/VART-wt-csf && source .venv/bin/activate
mkdir -p "$TMPDIR/csf"
curl --fail --silent --show-error --location --output "$TMPDIR/csf/csf-2.0-export.xlsx" \
  'https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all'
python -m datakit.csf extract "$TMPDIR/csf/csf-2.0-export.xlsx" --retrieved "$(date -u +%F)"
python -c "import json; d = json.load(open('data/csf/source/csf-2.0-extract.json')); print(len(d['outcomes']), d['sha256'][:12])"
```

Expected: `wrote data/csf/source/csf-2.0-extract.json`, then `106 <hash>`. A count other than 106 means NIST changed the Core: stop and tell Tarun (the tiers below assume this list). The xlsx stays in `$TMPDIR`; it is never committed.

- [ ] **Step 5: Write `data/csf/tiers.yaml`**

```yaml
# VART's part of data/csf/csf-2.0.json (CSF spec 4): the outcomes v1 checks against a company's documents
# (checked), the ones it asks the visitor about (ask), and the fixed question for each. Every other outcome is
# not_checked: stored with NIST's text and links, no question, no model call, no label. Moving an outcome into
# checked is a data change plus a control in data/dev/gap/facts.yaml; python -m datakit.csf build, then
# python -m datakit.gap dev, then re-record the gap-dev eval.
# Questions are generic paraphrases of NIST's outcome, never tuned to one document (CSF spec 10).
#
# Change log (one line per NIST refresh or tier change):
#   2026-10-05  first version: CSF 2.0 Reference Tool export, 106 outcomes, SP 800-53 Rev 5.2.0 references.
checked:
  GV.PO-01: "Is there a documented cybersecurity policy, based on the organization's context and strategy, that is communicated and enforced?"
  GV.PO-02: "Are cybersecurity policies reviewed, updated, communicated and enforced on a regular schedule?"
  ID.AM-01: "Is an inventory of the organization's hardware assets maintained?"
  ID.AM-02: "Is an inventory of the organization's software, services and systems maintained?"
  ID.AM-03: "Are diagrams or other representations of the organization's network communication and data flows maintained?"
  ID.AM-05: "Are assets and data prioritized by classification, criticality and impact?"
  ID.AM-08: "Are systems, hardware, software and data managed through their whole life cycle, including secure disposal?"
  ID.RA-01: "Are vulnerabilities in the organization's assets identified, validated and recorded, for example through scans or penetration tests?"
  ID.RA-02: "Does the organization receive cyber threat intelligence from information sharing forums or other sources?"
  ID.RA-08: "Is there a process for receiving, analyzing and responding to vulnerability reports from outside the organization?"
  PR.AA-01: "Are identities and credentials for users, services and hardware managed by the organization?"
  PR.AA-03: "Are users, services and hardware authenticated, including with multi-factor authentication?"
  PR.AA-05: "Are access permissions defined in a policy, managed, enforced and reviewed, following least privilege and separation of duties?"
  PR.AA-06: "Is physical access to offices, facilities and other assets managed, monitored and enforced?"
  PR.DS-01: "Is data at rest protected, for example by encryption?"
  PR.DS-02: "Is data in transit protected, for example by encryption?"
  PR.DS-11: "Are backups of data created, protected, maintained and tested?"
  PR.PS-01: "Are configuration and change management practices established and applied to production systems?"
  PR.PS-02: "Is software maintained, patched and replaced according to risk?"
  PR.PS-04: "Are log records generated and made available for continuous monitoring?"
  PR.PS-06: "Are secure software development practices, such as security testing and code review, part of the software development life cycle?"
  PR.IR-03: "Are resilience requirements, such as recovery objectives, defined and met in normal and adverse situations?"
  PR.IR-04: "Is enough resource capacity maintained to keep the service available?"
  DE.CM-09: "Are computing hardware, software and runtime environments monitored to find vulnerabilities and potentially adverse events?"
  DE.AE-06: "Is information about security events provided to the staff and tools that need it, for example through alerts?"
  DE.AE-07: "Is cyber threat intelligence integrated into the analysis of security events?"
  RS.MA-01: "Is there an incident response plan that is executed once an incident is declared?"
  RS.CO-02: "Are customers and other stakeholders notified of security incidents?"
  RC.RP-01: "Is the recovery part of the incident response or disaster recovery plan in place and exercised?"
ask:
  GV.OC-03: "Which legal, regulatory and contractual cybersecurity requirements apply to your organization, and how are they managed?"
  GV.RM-02: "Has your organization set risk appetite and risk tolerance statements for cybersecurity, and how are they communicated?"
  GV.RR-02: "Who holds cybersecurity roles and responsibilities in your organization, and how are they communicated and enforced?"
  GV.OV-01: "How does leadership review the results of the cybersecurity risk strategy and adjust it?"
  GV.SC-01: "Does your organization have a cybersecurity supply chain risk management program, and who agreed to it?"
```

- [ ] **Step 6: Build the file, register the validate stage, add the notice**

In `datakit/validate.py`, add `from datakit import csf` to the imports and, after the `mapper` stage:

```python
@stage("csf")
def _csf_stage(pack: str) -> list[str]:
    return csf.check()  # the CSF data is shared by every pack
```

Append to `data/NOTICE.md`:

```markdown
- **NIST CSF 2.0 Reference Tool export** (https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all,
  retrieved on the date in `data/csf/source/csf-2.0-extract.json`), public domain (U.S. Government work). The extract
  keeps NIST's outcome identifiers, function and category names, outcome text and SP 800-53 Rev 5.2.0 references,
  verbatim; the export's other informative references (ISO/IEC, PCI, CCM and others) are not kept. `tier` and
  `question` in `data/csf/csf-2.0.json` are this project's.
```

Run: `python -m datakit.csf build && pytest tests/datakit/test_csf.py -q && python -m datakit.validate csf`
Expected: `wrote data/csf/csf-2.0.json: 0 problems`, all tests PASS, `datakit.validate csf: 0 problems`.

- [ ] **Step 7: Tarun's review gate (the exact IDs)**

The lead sends Tarun one table: each Checked and Ask-me ID with NIST's outcome text (from `data/csf/csf-2.0.json`), VART's question, and, for Checked ones, the dev-pack control Task 5 will map it to and the label the key will expect (the table in Task 5 Step 3), plus decisions 1-6 from the execution notes and the coverage line `checked 29 · ask me 5 · not checked 72 · of 106`. Nothing is committed until he approves; his changes go into `tiers.yaml` (and into Task 5's outcome map), then Step 6 runs again.

- [ ] **Step 8: Commit**

Run the backend chain first (Global Constraints).

```bash
git add datakit/csf.py datakit/validate.py data/csf/source/csf-2.0-extract.json data/csf/tiers.yaml \
  data/csf/csf-2.0.json data/NOTICE.md tests/datakit/test_csf.py
git commit -m "feat(csf): NIST CSF 2.0 data with tiers and a drift check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `questionnaires.source` allows `'csf'`

**Reviewer:** Opus.

**Files:**
- Create: `migrations/versions/a7c3e9d1b2f4_questionnaires_csf_source.py`
- Modify: `app/db/models.py:133`, `tests/test_models.py`

**Interfaces:**
- Consumes: the migration head on `main` (`ffbf91b464dc` when this plan was written).
- Produces: `ck_questionnaires_source` = `source IN ('sample', 'upload', 'drive', 'csf')` in the models and the migrated database; pinned by the existing `test_migrated_check_constraints_match_the_models`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
def test_a_questionnaire_may_be_the_built_in_csf_one(s: Session) -> None:
    q = f.questionnaire(s, f.workspace(s), source="csf", filename="csf-2.0", mapping={"scope": "core"})
    s.commit()
    assert (q.source, q.mapping) == ("csf", {"scope": "core"})
```

(`ck_questionnaires_source` still refuses `email`: the existing parametrized `test_other_named_constraints_reject_bad_rows` keeps that case.)

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_models.py::test_a_questionnaire_may_be_the_built_in_csf_one -q`
Expected: FAIL, `IntegrityError ... ck_questionnaires_source`.

- [ ] **Step 3: Change the model and write the migration**

`app/db/models.py`, in `Questionnaire.__table_args__`:

```python
        CheckConstraint(_in("source", ("sample", "upload", "drive", "csf")), name="ck_questionnaires_source"),
```

Check the head first: `alembic heads` must print one revision. If it is not `ffbf91b464dc` (a later plan added a migration), use the printed one as `down_revision` below. Create `migrations/versions/a7c3e9d1b2f4_questionnaires_csf_source.py`:

```python
"""questionnaires csf source

Revision ID: a7c3e9d1b2f4
Revises: ffbf91b464dc
Create Date: 2026-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d1b2f4"
down_revision: Union[str, Sequence[str], None] = "ffbf91b464dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The built-in CSF gap-check questionnaire (CSF spec 6). Additive: no existing row changes."""
    op.drop_constraint("ck_questionnaires_source", "questionnaires", type_="check")
    op.create_check_constraint(
        "ck_questionnaires_source", "questionnaires", "source IN ('sample', 'upload', 'drive', 'csf')"
    )


def downgrade() -> None:
    """Deletes the CSF questionnaires (their items, runs and answers cascade): the old check refuses them."""
    op.execute("DELETE FROM questionnaires WHERE source = 'csf'")
    op.drop_constraint("ck_questionnaires_source", "questionnaires", type_="check")
    op.create_check_constraint(
        "ck_questionnaires_source", "questionnaires", "source IN ('sample', 'upload', 'drive')"
    )
```

- [ ] **Step 4: Run the tests and the round trip**

Run: `pytest tests/test_models.py -q && alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check`
Expected: all PASS (including `test_migrated_check_constraints_match_the_models`), the round trip runs without error, `No new upgrade operations detected.`

- [ ] **Step 5: Commit**

```bash
git add app/db/models.py migrations/versions/a7c3e9d1b2f4_questionnaires_csf_source.py tests/test_models.py
git commit -m "feat(db): questionnaires.source allows the built-in csf questionnaire" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Release note for 6B: this migration must reach production (`ops/setup.sh migrate`) before the code that writes a `'csf'` row is deployed (spec 10: additive changes first).

---

### Task 3: The framework in the app, scopes and gap labels

**Reviewer:** Sonnet.

**Files:**
- Create: `app/csf.py`, `tests/test_csf.py`
- Modify: `.vercelignore`

**Interfaces:**
- Consumes: `data/csf/csf-2.0.json` (Task 1's shape); `app.contracts.ItemInput`, `ItemLabel`, `Value`.
- Produces (in `app/csf.py`): `DATA: Path`; `Tier = Literal["checked", "ask", "not_checked"]`; `Scope = Literal["core", "govern", "identify", "protect", "detect", "respond", "recover"]`; `SCOPES: tuple[str, ...]`; `GapLabel = Literal["covered", "partly_covered", "not_met", "documents_disagree", "gap", "confirmed_by_you", "not_answered"]`; `GAP_WORDS: dict[str, str]`; `NOT_CHECKED = "not checked in this version"`; `@dataclass(frozen=True) Outcome(id, function, category, outcome, related_controls: tuple[str, ...], source_url, tier: Tier, question: str | None)`; `@dataclass(frozen=True) Framework(version, retrieved, outcomes: tuple[Outcome, ...])` with `get(csf_id) -> Outcome` (KeyError when unknown); `framework() -> Framework` (cached); `in_scope(scope: str) -> tuple[Outcome, ...]` (ValueError on an unknown scope); `item_input(o: Outcome) -> ItemInput`; `gap_label(o: Outcome, label: ItemLabel | None, value: Value | None = None, statement_id: object | None = None) -> GapLabel | None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_csf.py`:

```python
import uuid
from collections import Counter

import pytest

from app import csf
from app.contracts import ItemInput


def _one(tier: str) -> csf.Outcome:
    return next(o for o in csf.framework().outcomes if o.tier == tier)


def test_the_framework_holds_every_outcome_with_its_tier() -> None:
    fw = csf.framework()
    assert (len(fw.outcomes), fw.version) == (106, "2.0")
    assert Counter(o.tier for o in fw.outcomes) == {"checked": 29, "ask": 5, "not_checked": 72}
    assert all(o.question for o in fw.outcomes if o.tier != "not_checked")
    assert all(o.question is None for o in fw.outcomes if o.tier == "not_checked")
    assert fw.get("PR.AA-05").function == "Protect" and "AC-06" in fw.get("PR.AA-05").related_controls
    with pytest.raises(KeyError):
        fw.get("PR.AA-99")


@pytest.mark.parametrize(
    ("label", "value", "want"),
    [
        ("verified", "Yes", "covered"),
        ("partial", "Partial", "partly_covered"),
        ("verified", "No", "not_met"),
        ("conflict", None, "documents_disagree"),
        ("unknown", None, "gap"),
        ("na", None, None),
        (None, None, None),  # not run yet
    ],
)
def test_gap_labels_map_decides_output_as_the_spec_table_says(
    label: str | None, value: str | None, want: str | None
) -> None:
    assert csf.gap_label(_one("checked"), label, value) == want  # type: ignore[arg-type]


def test_ask_me_is_confirmed_only_with_a_stored_statement() -> None:
    ask = _one("ask")
    assert csf.gap_label(ask, "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"
    assert csf.gap_label(ask, "user_confirmed", None, None) == "not_answered"
    assert csf.gap_label(ask, None) == "not_answered"
    assert csf.gap_label(ask, "verified", "Yes") == "not_answered"  # a document label never confirms an Ask-me
    assert csf.gap_label(_one("checked"), "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"


def test_not_checked_outcomes_never_carry_a_label() -> None:
    o = _one("not_checked")
    for label, value in (("verified", "Yes"), ("unknown", None), ("user_confirmed", None), (None, None)):
        assert csf.gap_label(o, label, value, uuid.uuid4()) is None  # type: ignore[arg-type]


def test_every_label_has_its_display_words() -> None:
    assert csf.GAP_WORDS == {
        "covered": "Covered",
        "partly_covered": "Partly covered",
        "not_met": "Not met (stated)",
        "documents_disagree": "Documents disagree",
        "gap": "Gap",
        "confirmed_by_you": "Confirmed by you",
        "not_answered": "Not answered",
    }


def test_a_scope_is_the_core_or_one_function() -> None:
    core = csf.in_scope("core")
    assert len(core) == 34 and all(o.tier != "not_checked" for o in core)
    assert {o.function for o in csf.in_scope("protect")} == {"Protect"}
    assert Counter(o.tier for o in csf.in_scope("govern")) == {"checked": 2, "ask": 5}
    for bad in ("Protect", "all", ""):
        with pytest.raises(ValueError, match="unknown scope"):
            csf.in_scope(bad)


def test_an_outcome_is_asked_as_its_question_with_its_category_as_topic() -> None:
    o = csf.framework().get("PR.DS-01")
    assert csf.item_input(o) == ItemInput("PR.DS-01", o.question, "Data Security")
    with pytest.raises(ValueError, match="no question"):
        csf.item_input(_one("not_checked"))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_csf.py -q`
Expected: FAIL, `ImportError: cannot import name 'csf' from 'app'`.

- [ ] **Step 3: Write `app/csf.py`**

```python
"""NIST CSF 2.0 gap check (CSF spec 4-6): the bundled outcomes, scopes, and the gap labels, a display mapping over
decide's output (decide itself does not change). data/csf/csf-2.0.json is built and drift-tested by
datakit/csf.py; the app only reads it."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from app.contracts import ItemInput, ItemLabel, Value

DATA = Path(__file__).resolve().parent.parent / "data" / "csf" / "csf-2.0.json"
Tier = Literal["checked", "ask", "not_checked"]
Scope = Literal["core", "govern", "identify", "protect", "detect", "respond", "recover"]
SCOPES: tuple[str, ...] = get_args(Scope)
GapLabel = Literal[
    "covered", "partly_covered", "not_met", "documents_disagree", "gap", "confirmed_by_you", "not_answered"
]
GAP_WORDS: dict[str, str] = {
    "covered": "Covered",
    "partly_covered": "Partly covered",
    "not_met": "Not met (stated)",
    "documents_disagree": "Documents disagree",
    "gap": "Gap",
    "confirmed_by_you": "Confirmed by you",
    "not_answered": "Not answered",
}
NOT_CHECKED = "not checked in this version"
_CHECKED: dict[tuple[str, str | None], GapLabel] = {  # CSF spec 5.3
    ("verified", "Yes"): "covered",
    ("partial", "Partial"): "partly_covered",
    ("verified", "No"): "not_met",
    ("conflict", None): "documents_disagree",
    ("unknown", None): "gap",
}


@dataclass(frozen=True)
class Outcome:
    id: str
    function: str
    category: str
    outcome: str  # NIST's text, verbatim
    related_controls: tuple[str, ...]
    source_url: str
    tier: Tier
    question: str | None  # VART's phrasing; None when not checked


@dataclass(frozen=True)
class Framework:
    version: str
    retrieved: str
    outcomes: tuple[Outcome, ...]

    def get(self, csf_id: str) -> Outcome:
        return {o.id: o for o in self.outcomes}[csf_id]


@cache
def framework() -> Framework:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    outcomes = tuple(
        Outcome(
            o["id"],
            o["function"],
            o["category"],
            o["outcome"],
            tuple(o["related_controls"]),
            o["source_url"],
            o["tier"],
            o["question"],
        )
        for o in raw["outcomes"]
    )
    return Framework(raw["csf_version"], raw["retrieved"], outcomes)


def in_scope(scope: str) -> tuple[Outcome, ...]:
    """The Checked and Ask-me outcomes of the whole core or of one function (CSF spec 5.1), in NIST's order."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}: one of {', '.join(SCOPES)}")
    return tuple(
        o for o in framework().outcomes if o.tier != "not_checked" and scope in ("core", o.function.lower())
    )


def item_input(o: Outcome) -> ItemInput:
    if o.question is None:
        raise ValueError(f"{o.id} has no question: it is {NOT_CHECKED}")
    return ItemInput(o.id, o.question, o.category)


def gap_label(
    o: Outcome, label: ItemLabel | None, value: Value | None = None, statement_id: object | None = None
) -> GapLabel | None:
    """No label for a not-checked outcome (CSF spec 5.5). Confirmed by you needs a stored statement (spec 5.4);
    an Ask-me outcome without one is Not answered. A Checked outcome maps decide's label and value (spec 5.3);
    `na` and an outcome not run yet have no label."""
    if o.tier == "not_checked":
        return None
    if label == "user_confirmed" and statement_id is not None:
        return "confirmed_by_you"
    if o.tier == "ask":
        return "not_answered"
    return _CHECKED.get((label or "", value))
```

`.vercelignore`: replace the line `data` with these four lines, and extend the first comment line with "; the gap check reads data/csf/csf-2.0.json at runtime (app/csf.py)":

```
data/*
!data/csf/
data/csf/*
!data/csf/csf-2.0.json
```

(6B's release preview confirms the file is in the function bundle; no endpoint reads it before 6B.)

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_csf.py -q && mypy app`
Expected: PASS; `Success: no issues found`.

- [ ] **Step 5: Commit**

```bash
git add app/csf.py tests/test_csf.py .vercelignore
git commit -m "feat(csf): framework loader, scopes and gap labels over decide's output" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The built-in questionnaire, the run path per tier, and Ask-me answers

**Reviewer:** Sonnet.

**Files:**
- Modify: `app/csf.py`, `tests/test_csf.py`

**Interfaces:**
- Consumes: Task 3's `framework`, `in_scope`, `item_input`, `gap_label`; `app.pipeline.answer_item(session, workspace_id, item, llm, models, spend) -> ItemResult`; `app.interview.plan_queue(items) -> list[QueueEntry]`; `app.ingest.store.store_statement(session, workspace_id, text, *, filename, today) -> Document`; `app.db.models.Questionnaire`, `Item`, `Workspace`.
- Produces: `FILENAME = "csf-2.0"`; `questionnaire_for(session: Session, workspace_id: uuid.UUID, scope: str) -> Questionnaire` (commits; `mapping = {"csf_version", "retrieved", "scope", "digest"}`; items: `position` 1.., `row_ref = code = csf_id = id`, `topic = category`, `question = question`); `check_outcome(session, workspace_id, o: Outcome, llm: LLMClient, models: Mapping[str, str], spend: Spend) -> ItemResult | None` (Checked: `answer_item`; Ask-me: `None`, no model call; not-checked: `ValueError`); `ask_queue(outcomes: Sequence[Outcome], asked: Mapping[str, int]) -> list[QueueEntry]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_csf.py` (and add the imports to the top of the file):

```python
import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import date

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.models import DocumentLine, Item, Questionnaire
from app.ingest.store import store_statement
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import FakeLLM

MODELS = {"stance": "m/stance", "draft": "m/draft"}
QUOTE = "Customer data at rest is encrypted with AES-256."


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def test_the_built_in_questionnaire_holds_one_item_per_outcome_in_scope(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "protect")
    items = s.scalars(select(Item).where(Item.questionnaire_id == q.id).order_by(Item.position)).all()
    want = csf.in_scope("protect")
    assert (q.source, q.filename, q.mapping["scope"], q.mapping["csf_version"]) == ("csf", "csf-2.0", "protect", "2.0")
    assert [(i.position, i.code, i.csf_id, i.row_ref) for i in items] == [
        (n, o.id, o.id, o.id) for n, o in enumerate(want, 1)
    ]
    assert [(i.topic, i.question) for i in items] == [(o.category, o.question) for o in want]


def test_the_questionnaire_is_reused_per_scope(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    first = csf.questionnaire_for(s, ws.id, "core").id
    assert csf.questionnaire_for(s, ws.id, "core").id == first
    assert csf.questionnaire_for(s, ws.id, "detect").id != first
    other = f.workspace(s)
    s.commit()
    assert csf.questionnaire_for(s, other.id, "core").id != first  # never another workspace's
    assert s.scalar(select(func.count(Questionnaire.id))) == 3


def test_a_changed_tier_list_gives_a_new_questionnaire(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = f.workspace(s)
    s.commit()
    first = csf.questionnaire_for(s, ws.id, "govern").id
    fw = csf.framework()
    reworded = replace(
        fw,
        outcomes=tuple(
            replace(o, question="Is the policy approved?") if o.id == "GV.PO-01" else o for o in fw.outcomes
        ),
    )
    monkeypatch.setattr(csf, "framework", lambda: reworded)
    q = csf.questionnaire_for(s, ws.id, "govern")
    assert q.id != first
    asked = s.scalar(select(Item.question).where(Item.questionnaire_id == q.id, Item.csf_id == "GV.PO-01"))
    assert asked == "Is the policy approved?"


def test_an_unknown_scope_creates_nothing(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    with pytest.raises(ValueError, match="unknown scope"):
        csf.questionnaire_for(s, ws.id, "Protect")
    assert s.scalar(select(func.count(Questionnaire.id))) == 0


def test_a_checked_outcome_runs_the_ordinary_pipeline(s: Session) -> None:
    ws = f.workspace(s)
    doc = f.document(s, ws, filename="crypto-policy.docx")
    f.chunk(s, doc, line_start=4, line_end=4, text=QUOTE)
    s.commit()
    stance = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
    draft = json.dumps({"text": f'Yes. The crypto policy says "{QUOTE}"'})
    llm = FakeLLM([stance, draft])
    o = csf.framework().get("PR.DS-01")
    r = csf.check_outcome(s, ws.id, o, llm, MODELS, spender(s, ws.id))
    assert r is not None and r.item == csf.item_input(o)
    assert csf.gap_label(o, r.decision.label, r.decision.value) == "covered"
    assert [req.step for req in llm.requests] == ["stance", "draft"]


def test_ask_me_and_not_checked_outcomes_never_reach_a_model(s: Session) -> None:
    ws = f.workspace(s)
    doc = f.document(s, ws)
    f.chunk(s, doc, text="Leadership sets the cybersecurity risk tolerance every year.")
    s.commit()
    llm = FakeLLM([])  # any model call raises AssertionError
    ask = next(o for o in csf.framework().outcomes if o.tier == "ask")
    assert csf.check_outcome(s, ws.id, ask, llm, MODELS, spender(s, ws.id)) is None
    unchecked = next(o for o in csf.framework().outcomes if o.tier == "not_checked")
    with pytest.raises(ValueError, match="not checked"):
        csf.check_outcome(s, ws.id, unchecked, llm, MODELS, spender(s, ws.id))
    assert llm.requests == []


def test_ask_me_outcomes_are_queued_once_and_an_answer_confirms_them(s: Session) -> None:
    core = csf.in_scope("core")
    queue = csf.ask_queue(core, {})
    assert [e.key for e in queue] == [o.id for o in core if o.tier == "ask"]
    assert all(e.reason == "unknown" and e.question == csf.framework().get(e.key).question for e in queue)
    assert "GV.RR-02" not in [e.key for e in csf.ask_queue(core, {"GV.RR-02": 1})]  # asked once already

    ws = f.workspace(s)
    s.commit()
    o = csf.framework().get("GV.RR-02")
    doc = store_statement(
        s, ws.id, "Dana Ortiz, Head of Security, owns the program.", filename="answer-GV.RR-02.txt",
        today=date(2026, 10, 5),
    )
    lines = s.scalars(select(DocumentLine.text).where(DocumentLine.document_id == doc.id)).all()
    assert doc.kind == "statement" and "Dana Ortiz" not in " ".join(lines)  # redacted before storage
    assert csf.gap_label(o, "user_confirmed", None, doc.id) == "confirmed_by_you"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_csf.py -q`
Expected: the Task 3 tests PASS; the new ones FAIL with `AttributeError: module 'app.csf' has no attribute 'questionnaire_for'` (and `check_outcome`, `ask_queue`).

- [ ] **Step 3: Add the three functions to `app/csf.py`**

Imports to add at the top:

```python
import hashlib
import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import ItemResult, OpenItem, QueueEntry, Spend
from app.db.models import Item, Questionnaire, Workspace
from app.interview import plan_queue
from app.llm.client import LLMClient
from app.pipeline import answer_item
```

(and `ItemInput, ItemLabel, Value` stay imported from `app.contracts`). Then, at the end of the module:

```python
FILENAME = "csf-2.0"


def _digest(outcomes: Sequence[Outcome]) -> str:
    rows = [[o.id, o.tier, o.question, o.category] for o in outcomes]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def questionnaire_for(session: Session, workspace_id: uuid.UUID, scope: str) -> Questionnaire:
    """The workspace's built-in CSF questionnaire for `scope` (CSF spec 6), created on first use with one item
    per Checked and Ask-me outcome in scope. It is reused only while the CSF data behind it is the same (version,
    retrieval date, scope and a digest of the items), so a deploy that changes the tiers or a question gives the
    next run new items instead of stale ones. Commits."""
    outcomes = in_scope(scope)
    fw = framework()
    mapping = {"csf_version": fw.version, "retrieved": fw.retrieved, "scope": scope, "digest": _digest(outcomes)}
    # Lock the workspace row, as ingest does, so two first calls at once create one questionnaire.
    session.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    q = session.scalars(
        select(Questionnaire).where(
            Questionnaire.workspace_id == workspace_id,
            Questionnaire.source == "csf",
            Questionnaire.mapping == mapping,
        )
    ).first()
    if q is None:
        q = Questionnaire(workspace_id=workspace_id, filename=FILENAME, source="csf", mapping=mapping)
        session.add(q)
        session.flush()
        session.add_all(
            Item(
                workspace_id=workspace_id,
                questionnaire_id=q.id,
                position=n,
                row_ref=o.id,
                code=o.id,
                csf_id=o.id,
                topic=o.category,
                question=item_input(o).question,
            )
            for n, o in enumerate(outcomes, 1)
        )
    session.commit()
    return q


def check_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult | None:
    """One outcome of a gap-check run (CSF spec 5.2-5.5). Checked: answer_item unchanged (it spends before each
    model call and holds no transaction across one). Ask me: None, with no retrieval and no model call; the
    visitor answers it through ask_queue and store_statement. Not checked: never part of a run."""
    if o.tier == "checked":
        return answer_item(session, workspace_id, item_input(o), llm, models, spend)
    if o.tier == "ask":
        return None
    raise ValueError(f"{o.id} is {NOT_CHECKED}")


def ask_queue(outcomes: Sequence[Outcome], asked: Mapping[str, int]) -> list[QueueEntry]:
    """Questions for you (CSF spec 5.4): the Ask-me outcomes, through the interview planner, so an outcome
    already asked (`asked[id] >= 1`) is not queued again. An answer is stored with store_statement (redacted)
    and shows Confirmed by you through gap_label, citing that statement."""
    return plan_queue(
        [OpenItem(item_input(o), "unknown", asked.get(o.id, 0), o.question or "") for o in outcomes if o.tier == "ask"]
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_csf.py tests/test_pipeline.py -q && mypy app`
Expected: PASS; `Success: no issues found`.

- [ ] **Step 5: Commit**

```bash
git add app/csf.py tests/test_csf.py
git commit -m "feat(csf): built-in questionnaire per scope, run path per tier, Ask-me queue" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The gap extension and the code-derived key

**Reviewer:** Opus.

**Files:**
- Modify: `datakit/schemas.py`, `datakit/validate.py`
- Create: `datakit/gap.py`, `data/dev/gap/facts.yaml`, `data/dev/gap/docs/security-improvement-plan.md`, `tests/datakit/test_gap.py`
- Create (written by `python -m datakit.gap dev`): `data/dev/key/csf-core.yaml`

**Interfaces:**
- Consumes: `datakit.derive_key.derive(f, sel) -> Key`; `datakit.validate.check_facts(f) -> list[str]`; `datakit.extract.lines_of(path) -> list[str]`; `app.csf.framework`, `gap_label`, `Outcome`; `app.text.contains`.
- Produces: `datakit.schemas.GapOutcome(csf_id, control)`, `GapFacts(pack, documents, controls, statements, traps, outcomes)`; `TrapKind` gains `"planned_only"`; in `datakit/gap.py`: `NAME = "csf-core"`, `gap_dir(pack) -> Path`, `load(pack) -> tuple[Facts, GapFacts]`, `merged(facts, gap) -> Facts`, `checked() -> list[Outcome]`, `selection(facts, gap) -> Selection`, `derive_gap(facts, gap) -> Key`, `doc_path(pack, gap, spec) -> Path`, `trap_sources(f: Facts, control: str) -> set[str]` (subset of `{"template", "draft", "planned"}`, empty when any final usable statement exists), `check(pack) -> list[str]`, `main(pack) -> None`; validate stage `gap`.

The planted cases, all derived by `derive_key`'s rules (nobody writes a label):

| Outcome | Control | Expected (decide) | Gap label | Why |
|---|---|---|---|---|
| GV.PO-01, GV.PO-02, ID.AM-01, ID.AM-02, ID.AM-05, ID.AM-08, ID.RA-01, ID.RA-08, PR.AA-01, PR.DS-01, PR.DS-02, PR.DS-11, PR.PS-01, PR.PS-02, PR.PS-04, PR.PS-06, PR.IR-03, DE.CM-09, RC.RP-01 | infosec-program, policy-review, asset-inventory, asset-inventory, data-classification, media-sanitization, pentest, vuln-disclosure, sso, encryption-at-rest, encryption-in-transit, backups, build-release, patch-sla, central-logging, sast, rto-rpo, vuln-scanning, dr-test | verified Yes | Covered | final, usable yes statements (GV.PO-02 and ID.RA-01 also carry a placeholder sentence, P2 and P1, that must not be cited) |
| PR.AA-03 | mfa | partial | Partly covered | scope trap S1 |
| RS.MA-01 | ir-plan | partial | Partly covered | trap: only a draft speaks (R2) |
| RS.CO-02 | breach-notification | partial | Partly covered | trap: only a draft and a contract template speak |
| PR.AA-05 | access-review | conflict | Documents disagree | D1: the policy says quarterly, the newer log shows every review overdue |
| DE.AE-06 | alerting | conflict | Documents disagree | G1 (new): the logging policy says alerts page on-call; the improvement plan says not yet |
| ID.RA-02 | threat-intel-sources (new) | verified No | Not met (stated) | trap G2: planned only |
| DE.AE-07 | threat-intel-analysis (new) | verified No | Not met (stated) | trap G3: planned only |
| ID.AM-03 | data-flow-diagram | unknown | Gap | no document mentions data flows (the dev keyword net, M11) |
| PR.AA-06 | physical-access | unknown | Gap | no document mentions physical access (the dev keyword net, M10) |
| PR.IR-04 | uptime-sla | unknown | Gap | trap: only the contract template speaks (M6) |

- [ ] **Step 1: Write the failing tests**

`tests/datakit/test_gap.py`:

```python
from collections import Counter
from datetime import date

import pytest

from app.classify import rules
from app.contracts import DocMeta
from app.csf import framework, gap_label
from datakit import gap
from datakit.extract import lines_of
from datakit.schemas import Facts
from datakit.validate import STAGES, check_facts


def _labels() -> dict[str, str | None]:
    facts, g = gap.load("dev")
    return {k.code: gap_label(framework().get(k.code), k.expected_label, k.expected_value) for k in gap.derive_gap(facts, g).items}


def test_the_gap_stage_passes_on_the_dev_pack() -> None:
    assert STAGES["gap"]("dev") == []


def test_the_key_plants_what_the_spec_asks() -> None:
    labels = _labels()
    assert len(labels) == 29 and set(labels) == {o.id for o in gap.checked()}
    by_label: dict[str | None, set[str]] = {}
    for code, label in labels.items():
        by_label.setdefault(label, set()).add(code)
    assert by_label["documents_disagree"] == {"PR.AA-05", "DE.AE-06"}
    assert by_label["not_met"] == {"ID.RA-02", "DE.AE-07"}
    assert by_label["gap"] == {"ID.AM-03", "PR.AA-06", "PR.IR-04"}
    assert by_label["partly_covered"] == {"PR.AA-03", "RS.MA-01", "RS.CO-02"}
    assert Counter(labels.values())["covered"] == 17


def test_trap_outcomes_are_never_expected_covered() -> None:
    facts, g = gap.load("dev")
    f = gap.merged(facts, g)
    control = {m.csf_id: m.control for m in g.outcomes}
    sources = {c: gap.trap_sources(f, control[c]) for c in control}
    assert {c: s for c, s in sources.items() if s} == {
        "ID.RA-02": {"planned"},
        "DE.AE-07": {"planned"},
        "RS.MA-01": {"draft"},
        "RS.CO-02": {"draft", "template"},
        "PR.IR-04": {"template"},
    }
    labels = _labels()
    assert all(labels[c] != "covered" for c, s in sources.items() if s)


def test_the_dev_keys_and_fact_sheet_do_not_change() -> None:
    facts, g = gap.load("dev")
    assert STAGES["keys"]("dev") == []  # vsq-a and mvsp-b are derived from the dev sheet alone
    assert not {d.id for d in g.documents} & {d.id for d in facts.documents}


def test_a_planned_only_statement_must_be_a_negated_no_in_a_final_document() -> None:
    facts, g = gap.load("dev")
    data = gap.merged(facts, g).model_dump()
    for s in data["statements"]:
        if s["id"] == "sip-threat-intel-sources":
            s["stance"], s["flags"] = "partial", []
    assert "trap G2: planned-only statements must be flagged negation, stance no, in a final document" in check_facts(
        Facts.model_validate(data)
    )


def test_an_unmapped_checked_outcome_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    facts, g = gap.load("dev")
    short = g.model_copy(update={"outcomes": g.outcomes[1:]})
    monkeypatch.setattr(gap, "load", lambda pack: (facts, short))
    assert gap.check("dev") == [f"Checked outcome {g.outcomes[0].csf_id} has no control"]


def test_the_improvement_plan_is_classified_by_rules_alone() -> None:
    facts, g = gap.load("dev")
    spec = g.documents[0]
    meta, sure = rules("md", lines_of(gap.doc_path("dev", g, spec)))
    assert sure and meta == DocMeta("plan", "final", date(2026, 7, 1), None, True, "rule")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/datakit/test_gap.py -q`
Expected: FAIL, `ImportError: cannot import name 'gap' from 'datakit'`.

- [ ] **Step 3: The schema, the trap rule, the data**

`datakit/schemas.py`: add `"planned_only",` to `TrapKind` after `"draft_only",`, and after `class Key`:

```python
class GapOutcome(_Strict):
    csf_id: str
    control: str


class GapFacts(_Strict):
    """data/<pack>/gap/facts.yaml: what only the CSF gap check adds to the pack's fact sheet (datakit.gap)."""

    pack: str
    documents: tuple[DocSpec, ...] = ()
    controls: tuple[Control, ...] = ()
    statements: tuple[Statement, ...] = ()
    traps: tuple[Trap, ...] = ()
    outcomes: tuple[GapOutcome, ...]
```

`datakit/validate.py`, in `check_facts`, after the `draft_only` rule:

```python
        if t.kind == "planned_only" and not all(
            "negation" in s.flags and s.stance == "no" and f.doc(s.doc).status == "final" for s in ss
        ):
            p.append(f"trap {t.id}: planned-only statements must be flagged negation, stance no, in a final document")
```

`data/dev/gap/docs/security-improvement-plan.md` (ASCII, exactly):

```markdown
# Security Improvement Plan

Kestrelyn, Inc. - Version 1.0 - Effective 2026-07-01

## Threat Intelligence

Kestrelyn does not yet receive cyber threat intelligence from information sharing forums; joining an industry sharing group is planned for 2027.

Threat intelligence is not yet integrated into the analysis of security events; this integration is planned for 2027.

## Alerting

Security alerts are not yet routed to the on-call rotation; on-call paging for security alerts is planned for 2027.
```

`data/dev/gap/facts.yaml`:

```yaml
# Gap-check extension of data/dev/facts.yaml (datakit.gap). Read only by the CSF gap check (eval pack gap-dev), so
# the questionnaire keys, the dev eval and its recordings do not change. Same rules as the dev fact sheet: a
# statement appears verbatim in its document; ASCII only.
#   outcomes  every Checked CSF 2.0 outcome (data/csf/tiers.yaml) and the one control that answers it
pack: dev

documents:
  - id: sip
    filename: security-improvement-plan.md
    format: md
    kind: plan
    effective_date: 2026-07-01

controls:
  - {id: threat-intel-sources, topic: Detection, truth: "No threat intelligence feed yet; joining a sharing group is planned for 2027"}
  - {id: threat-intel-analysis, topic: Detection, truth: "Threat intelligence is not yet used in event analysis; planned for 2027"}

statements:
  - id: sip-threat-intel-sources
    doc: sip
    control: threat-intel-sources
    stance: no
    flags: [negation]
    text: "Kestrelyn does not yet receive cyber threat intelligence from information sharing forums; joining an industry sharing group is planned for 2027."
  - id: sip-threat-intel-analysis
    doc: sip
    control: threat-intel-analysis
    stance: no
    flags: [negation]
    text: "Threat intelligence is not yet integrated into the analysis of security events; this integration is planned for 2027."
  - id: sip-alerting
    doc: sip
    control: alerting
    stance: no
    flags: [negation]
    text: "Security alerts are not yet routed to the on-call rotation; on-call paging for security alerts is planned for 2027."

traps:
  - id: G1
    kind: disagree
    statements: [lmp-alerting, sip-alerting]
    note: "The logging policy says security events page the on-call rotation; the improvement plan says alerts are not yet routed to it."
  - id: G2
    kind: planned_only
    statements: [sip-threat-intel-sources]
    note: "Receiving threat intelligence is only planned: a stated non-compliance, never Covered."
  - id: G3
    kind: planned_only
    statements: [sip-threat-intel-analysis]
    note: "Using threat intelligence in event analysis is only planned: a stated non-compliance, never Covered."
  - id: G4
    kind: planned_only
    statements: [sip-alerting]
    note: "On-call paging for security alerts is only planned in the improvement plan."

outcomes:
  - {csf_id: GV.PO-01, control: infosec-program}
  - {csf_id: GV.PO-02, control: policy-review}
  - {csf_id: ID.AM-01, control: asset-inventory}
  - {csf_id: ID.AM-02, control: asset-inventory}
  - {csf_id: ID.AM-03, control: data-flow-diagram}
  - {csf_id: ID.AM-05, control: data-classification}
  - {csf_id: ID.AM-08, control: media-sanitization}
  - {csf_id: ID.RA-01, control: pentest}
  - {csf_id: ID.RA-02, control: threat-intel-sources}
  - {csf_id: ID.RA-08, control: vuln-disclosure}
  - {csf_id: PR.AA-01, control: sso}
  - {csf_id: PR.AA-03, control: mfa}
  - {csf_id: PR.AA-05, control: access-review}
  - {csf_id: PR.AA-06, control: physical-access}
  - {csf_id: PR.DS-01, control: encryption-at-rest}
  - {csf_id: PR.DS-02, control: encryption-in-transit}
  - {csf_id: PR.DS-11, control: backups}
  - {csf_id: PR.PS-01, control: build-release}
  - {csf_id: PR.PS-02, control: patch-sla}
  - {csf_id: PR.PS-04, control: central-logging}
  - {csf_id: PR.PS-06, control: sast}
  - {csf_id: PR.IR-03, control: rto-rpo}
  - {csf_id: PR.IR-04, control: uptime-sla}
  - {csf_id: DE.CM-09, control: vuln-scanning}
  - {csf_id: DE.AE-06, control: alerting}
  - {csf_id: DE.AE-07, control: threat-intel-analysis}
  - {csf_id: RS.MA-01, control: ir-plan}
  - {csf_id: RS.CO-02, control: breach-notification}
  - {csf_id: RC.RP-01, control: dr-test}
```

- [ ] **Step 4: Write `datakit/gap.py` and the validate stage**

```python
"""The CSF gap-check answer key (CSF spec 8). data/<pack>/gap/facts.yaml extends the pack's fact sheet with what
only the gap check uses (documents, controls, statements, traps) and maps each Checked CSF outcome to the one
control that answers it. The key comes from derive_key's rules over the merged sheet, so it agrees with the
documents by construction: nobody writes an answer to match the engine.   python -m datakit.gap dev"""

import sys
from pathlib import Path

from app.csf import Outcome, framework, gap_label
from app.text import contains
from datakit.derive_key import derive
from datakit.extract import lines_of
from datakit.schemas import DocSpec, Facts, GapFacts, Key, Selection, SelectionItem, dump_yaml, load_yaml

ROOT = Path(__file__).resolve().parent.parent
NAME = "csf-core"
MIN_PLANTED = {"documents_disagree": 2, "not_met": 2, "gap": 2}  # CSF spec 8
TRAP_SOURCES = ("template", "draft", "planned")


def gap_dir(pack: str) -> Path:
    return ROOT / "data" / pack / "gap"


def load(pack: str) -> tuple[Facts, GapFacts]:
    return (
        load_yaml(ROOT / "data" / pack / "facts.yaml", Facts),
        load_yaml(gap_dir(pack) / "facts.yaml", GapFacts),
    )


def merged(facts: Facts, gap: GapFacts) -> Facts:
    data = facts.model_dump()
    extra = gap.model_dump()
    for field in ("documents", "controls", "statements", "traps"):
        data[field] = [*data[field], *extra[field]]
    return Facts.model_validate(data)


def checked() -> list[Outcome]:
    return [o for o in framework().outcomes if o.tier == "checked"]


def selection(facts: Facts, gap: GapFacts) -> Selection:
    control = {m.csf_id: m.control for m in gap.outcomes}
    return Selection(
        questionnaire=NAME,
        title="NIST CSF 2.0 core",
        buyer=facts.buyer,
        items=tuple(
            SelectionItem(
                code=o.id,
                section=o.category,
                question=o.question or "",
                source=f"csf:{o.id}",
                csf_id=o.id,
                control=control[o.id],
            )
            for o in checked()
        ),
    )


def derive_gap(facts: Facts, gap: GapFacts) -> Key:
    return derive(merged(facts, gap), selection(facts, gap))


def doc_path(pack: str, gap: GapFacts, spec: DocSpec) -> Path:
    base = gap_dir(pack) if spec.id in {d.id for d in gap.documents} else ROOT / "data" / pack
    return base / "docs" / spec.filename


def trap_sources(f: Facts, control: str) -> set[str]:
    """Why an outcome is a trap (CSF spec 8): every statement about its control is in a template (or has a
    placeholder), in a draft, or only planned. Empty when any final, usable statement speaks to it."""
    planned = {s for t in f.traps if t.kind == "planned_only" for s in t.statements}
    out: set[str] = set()
    for s in f.statements_for(control):
        doc = f.doc(s.doc)
        if not doc.evidence_allowed or "placeholder" in s.flags:
            out.add("template")
        elif doc.status == "draft":
            out.add("draft")
        elif s.id in planned:
            out.add("planned")
        else:
            return set()
    return out


def check(pack: str) -> list[str]:
    from datakit.validate import check_facts  # validate imports this module

    facts, gap = load(pack)
    f = merged(facts, gap)
    if p := check_facts(f):
        return p
    ids = [m.csf_id for m in gap.outcomes]
    want = {o.id for o in checked()}
    controls = {c.id for c in f.controls}
    p += [f"outcome {i} is mapped twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    p += [f"Checked outcome {i} has no control" for i in sorted(want - set(ids))]
    p += [f"outcome {i} is not a Checked CSF outcome" for i in sorted(set(ids) - want)]
    p += [f"outcome {m.csf_id}: unknown control {m.control}" for m in gap.outcomes if m.control not in controls]
    if p:
        return p
    lines = {d.id: lines_of(doc_path(pack, gap, d)) for d in f.documents}
    p += [
        f"statement {s.id} not found verbatim in {f.doc(s.doc).filename}"
        for s in gap.statements
        if not any(contains(line, s.text) for line in lines[s.doc])
    ]
    p += [f"{d.filename} is not ASCII" for d in gap.documents if not doc_path(pack, gap, d).read_bytes().isascii()]
    key = derive_gap(facts, gap)
    path = ROOT / "data" / pack / "key" / f"{NAME}.yaml"
    if not path.exists() or load_yaml(path, Key) != key:
        p.append(f"key {NAME} is stale: run python -m datakit.gap {pack}")
    p += [
        f"{k.code}: evidence not found in {f.doc(e.doc).filename}"
        for k in key.items
        for e in k.evidence
        if not any(contains(line, e.quote) for line in lines[e.doc])
    ]
    p += [
        f"{k.code}: conflict without a planted trap"
        for k in key.items
        if k.expected_label == "conflict" and k.conflict_trap is None
    ]
    labels: list[str | None] = [
        gap_label(framework().get(k.code), k.expected_label, k.expected_value) for k in key.items
    ]
    p += [
        f"only {labels.count(x)} {x} outcome(s) planted, need {n}"
        for x, n in MIN_PLANTED.items()
        if labels.count(x) < n
    ]
    control = {m.csf_id: m.control for m in gap.outcomes}
    found = set().union(*(trap_sources(f, control[k.code]) for k in key.items))
    p += [f"no trap outcome where only a {s} source speaks" for s in TRAP_SOURCES if s not in found]
    return p


def main(pack: str) -> None:
    facts, gap = load(pack)
    dump_yaml(derive_gap(facts, gap), ROOT / "data" / pack / "key" / f"{NAME}.yaml")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
```

`datakit/validate.py`: add `from datakit import gap` to the imports and, after the `csf` stage:

```python
@stage("gap")
def _gap_stage(pack: str) -> list[str]:
    return gap.check(pack)
```

- [ ] **Step 5: Derive the key and run the tests**

Run: `python -m datakit.gap dev && pytest tests/datakit -q && python -m datakit.validate all`
Expected: `data/dev/key/csf-core.yaml` written; all tests PASS; `datakit.validate all: 0 problems`.

- [ ] **Step 6: Commit**

```bash
git add datakit/schemas.py datakit/validate.py datakit/gap.py data/dev/gap/facts.yaml \
  data/dev/gap/docs/security-improvement-plan.md data/dev/key/csf-core.yaml tests/datakit/test_gap.py
git commit -m "feat(csf): gap extension of the dev fact sheet and the code-derived csf-core key" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The `gap-dev` eval pack and its gates

**Reviewer:** Opus.

**Files:**
- Create: `evals/gap.py`, `evals/fixtures/gap-dev-answers.json`, `tests/test_eval_gap.py`
- Modify: `evals/run.py` (`main` dispatch and output names), `evals/score.py` (`gates` takes a table)

**Interfaces:**
- Consumes: `app.csf` (Tasks 3-4); `datakit.gap.load`, `merged`, `doc_path`, `trap_sources`, `NAME` and `datakit.csf.check` (Tasks 1, 5); `evals.pack.load("dev")`, `Pack.private_strings()`; `evals.score._gated`, `_count`, `_citation_counts`, `_found`, `markdown`, `gates`; `evals.run.Log`, `_stored`, `_leaks` (imported inside `evals.gap.run`, since `evals.run` imports `evals.gap`); `app.ingest.store.ingest_document`, `store_statement`.
- Produces: `evals.gap.NAME = "gap-dev"`, `GATES`, `STATEMENT_DATE`, `SECRETS`, `always`, `@dataclass(frozen=True) GapPack(dev, gap, facts, control, keys)`, `@dataclass GapObserved(results, labels, items, statements, kinds, doc_ids, stored, leaks, private)`, `load() -> GapPack`, `run(llm, models) -> dict[str, Any]`, `score_gap(pack, obs) -> dict[str, float | None]`, `misses(pack, obs) -> list[str]`; `evals.score.gates(metrics, table=None)`; `python -m evals.run --pack gap-dev` writes `evals/results/gap-dev.{json,md}` and records to `evals/recorded/gap-dev.jsonl`.

Gates (CSF spec 8), each failing closed (`None`) when there is nothing to measure:

| Gate | Metric | Rule |
|---|---|---|
| Cited coverage | `cited_coverage` | every Covered and Partly covered result cites a stored line holding its quote: >= 1.0 |
| Trap coverage | `trap_coverage` | trap outcomes shown as Covered, plus Covered or Partly citations of a non-evidence document: <= 0 |
| Label accuracy | `label_accuracy` | gap labels on Checked outcomes: >= 0.80 (tightened after the baseline) |
| Disagreements caught | `disagreements_caught` | recall on expected Documents disagree: >= 1.0 |
| Stated non-compliance | `stated_noncompliance` | recall on expected Not met: >= 1.0 |
| NIST text intact | `nist_text_intact` | `datakit.csf.check()` finds nothing: >= 1.0 |
| Honest tiers | `honest_tiers` | not-checked outcomes are no item and carry no label; Ask-me labels only from a stored statement: >= 1.0 |
| Redaction | `redaction_private_leaks` | private strings of the Ask-me answers in stored statements or any model request: <= 0 |
| Cost and speed | `cost_usd_per_core_run`, `seconds_per_core_run` | reported (one run, so its seconds are the p50) |
| Retrieval | `retrieval_recall_at_8` | reported (CSF spec 10: phrasings are measured) |

- [ ] **Step 1: The fixture**

`evals/fixtures/gap-dev-answers.json` (GV.OV-01 is left unanswered on purpose; the names, email, phone and key are planted for the redaction gate):

```json
{
  "GV.OC-03": "Kestrelyn follows HIPAA for its healthcare customers and the security terms in each customer agreement. Dana Ortiz, Head of Security, reviews these requirements every year.",
  "GV.RM-02": "Yes. The CEO approved a cybersecurity risk tolerance statement in March 2026, and it is shared with every team lead. Questions go to dana.ortiz@kestrelyn.example.",
  "GV.RR-02": "Dana Ortiz, Head of Security, owns the security program and Priya Raman, CTO, owns engineering security. Reach Dana at +1 512 555 0142.",
  "GV.SC-01": "The vendor risk management policy is our supply chain program; the CEO approved it in February 2026. Our vendor portal api_key=sk9Kestrel2026xQ is rotated monthly."
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_eval_gap.py`:

```python
import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import Citation, Decision, Draft, ItemInput, ItemResult, Retrieval
from app.db.models import Document, Workspace
from evals import gap, run, score
from tests.fakes import FakeLLM

MODELS = {"stance": "m/s", "draft": "m/d", "classify": "m/c", "judge": "m/j", "recheck": "m/r"}
UNKNOWN = Decision("unknown", None, (), (), None, None, 0.0)


def _result(code: str, decision: Decision) -> ItemResult:
    return ItemResult(ItemInput(code, "q", None), Retrieval((), ()), (), decision, Draft("", "none"), 0.01, 1000)


def _perfect(pack: gap.GapPack) -> gap.GapObserved:
    """What a flawless engine would produce: each key's label, citing each key quote from a stored line."""
    results: dict[str, ItemResult] = {}
    stored: dict[str, list[str]] = {}
    for code, k in pack.keys.items():
        cites = []
        for e in k.evidence:
            lines = stored.setdefault(f"d-{e.doc}", [])
            lines.append(e.quote)
            cites.append(Citation("c", f"d-{e.doc}", e.doc, len(lines), len(lines), e.quote, e.stance))
        cited = tuple(cites) if k.expected_label != "unknown" else ()
        results[code] = _result(code, Decision(k.expected_label, k.expected_value, cited, (), None, None, 0.9))
    labels = {o.id: csf.gap_label(o, None) for o in csf.framework().outcomes}
    labels["GV.OC-03"] = "confirmed_by_you"
    return gap.GapObserved(
        results=results,
        labels=labels,
        items=[o.id for o in csf.in_scope("core")],
        statements={"GV.OC-03": "s1"},
        kinds={"s1": "statement"},
        doc_ids={d.id: f"d-{d.id}" for d in pack.facts.documents},
        stored=stored,
        leaks=0,
        private=4,
    )


def _with(obs: gap.GapObserved, code: str, decision: Decision) -> gap.GapObserved:
    return replace(obs, results={**obs.results, code: _result(code, decision)})


def test_a_flawless_run_passes_every_gate() -> None:
    pack = gap.load()
    m = gap.score_gap(pack, _perfect(pack))
    assert all(g["pass"] for g in score.gates(m, gap.GATES).values()), m
    assert m["label_accuracy"] == 1.0 and m["cost_usd_per_core_run"] == 0.29


def test_a_trap_outcome_shown_as_covered_fails_trap_coverage() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    draft_only = obs.results["RS.MA-01"].decision
    obs = _with(obs, "RS.MA-01", replace(draft_only, label="verified", value="Yes"))
    m = gap.score_gap(pack, obs)
    assert m["trap_coverage"] == 1.0 and not score.gates(m, gap.GATES)["trap_coverage"]["pass"]


def test_a_missed_disagreement_and_a_missed_non_compliance_fail_their_recall() -> None:
    pack = gap.load()
    obs = _with(_with(_perfect(pack), "PR.AA-05", UNKNOWN), "ID.RA-02", UNKNOWN)
    m = gap.score_gap(pack, obs)
    assert (m["disagreements_caught"], m["stated_noncompliance"]) == (0.5, 0.5)
    assert gap.misses(pack, obs) == ["ID.RA-02: expected not_met, got gap", "PR.AA-05: expected documents_disagree, got gap"]


def test_an_ask_me_label_without_a_statement_fails_honest_tiers() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    assert gap.score_gap(pack, replace(obs, labels={**obs.labels, "GV.OV-01": "confirmed_by_you"}))["honest_tiers"] < 1
    assert gap.score_gap(pack, replace(obs, items=[*obs.items, "GV.OC-01"]))["honest_tiers"] < 1  # a not-checked item
    assert gap.score_gap(pack, replace(obs, kinds={"s1": "policy"}))["honest_tiers"] < 1  # not a statement


def test_gates_fail_closed_when_there_is_nothing_to_measure() -> None:
    pack = replace(gap.load(), keys={})
    obs = replace(_perfect(gap.load()), results={}, private=0)
    g = score.gates(gap.score_gap(pack, obs), gap.GATES)
    for name in ("cited_coverage", "trap_coverage", "label_accuracy", "disagreements_caught",
                 "stated_noncompliance", "redaction_private_leaks"):
        assert g[name]["value"] is None and not g[name]["pass"] and "nothing to measure" in g[name]["reason"]


def test_a_key_outcome_without_a_result_stops_the_scoring() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    with pytest.raises(ValueError, match="PR.DS-01"):
        gap.score_gap(pack, replace(obs, results={c: r for c, r in obs.results.items() if c != "PR.DS-01"}))


def test_run_answers_checked_outcomes_stores_ask_answers_and_deletes_its_workspace(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = gap.load()
    with Session(db) as s:
        other = Workspace()
        s.add(other)
        s.commit()
        bystander = other.id
    loaded: list[str] = []

    def ingest(session: Session, ws: uuid.UUID, filename: str, data: bytes, **kw: Any) -> Document:
        assert kw["source"] == "sample" and kw["spend"] is gap.always
        loaded.append(filename)
        d = Document(workspace_id=ws, filename=filename, source="sample", sha256="0" * 64, kind="policy")
        session.add(d)
        session.commit()
        return d

    def check(session: Any, ws: Any, o: csf.Outcome, llm: Any, models: Any, spend: Any) -> ItemResult | None:
        assert spend is gap.always
        return None if o.tier == "ask" else _result(o.id, UNKNOWN)

    monkeypatch.setattr(gap, "ingest_document", ingest)
    monkeypatch.setattr(csf, "check_outcome", check)
    llm = FakeLLM([])
    report = gap.run(llm, MODELS)

    assert loaded == [d.filename for d in pack.facts.documents]  # the 22 dev documents, then the plan
    assert sorted(report["items"]) == sorted(pack.keys) and llm.requests == []
    m = report["metrics"]
    assert (m["honest_tiers"], m["redaction_private_leaks"], m["nist_text_intact"]) == (1.0, 0.0, 1.0)
    assert m["label_accuracy"] == round(3 / 29, 4)  # only the three planted gaps are right
    assert set(report["gates"]) == set(gap.GATES) and set(report["models"]) == {"stance", "draft"}
    with Session(db) as s:
        assert s.scalars(select(Workspace.id)).all() == [bystander]


@pytest.mark.parametrize(("passing", "code"), [(True, 0), (False, 1)])
def test_main_writes_the_gap_pack_to_its_own_results_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, passing: bool, code: int
) -> None:
    monkeypatch.setattr(run, "RESULTS", tmp_path)
    monkeypatch.setattr(run, "RECORDED", tmp_path)
    metrics = {"label_accuracy": 0.9 if passing else 0.5}
    report = {"pack": "gap-dev", "models": {}, "prompts": [], "metrics": metrics,
              "gates": score.gates(metrics, {"label_accuracy": (">=", 0.8)}), "label_misses": []}
    monkeypatch.setattr(gap, "run", lambda llm, models: report)
    assert run.main(["--pack", "gap-dev"]) == code
    assert json.loads((tmp_path / "gap-dev.json").read_text())["pack"] == "gap-dev"
    assert (tmp_path / "gap-dev.md").read_text().startswith("# Eval results: gap-dev pack")
    assert not (tmp_path / "latest.json").exists()
```

(The cost assertion: 29 results at 0.01 USD each.)

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/test_eval_gap.py -q`
Expected: FAIL, `ImportError: cannot import name 'gap' from 'evals'`.

- [ ] **Step 4: `evals/score.py`: gates take a table**

Replace the first two lines of `gates`:

```python
def gates(
    metrics: dict[str, float | None], table: dict[str, tuple[str, float]] | None = None
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, (op, target) in (table or GATES).items():
```

(the rest of the function is unchanged; `None` keeps the dev pack's `GATES`).

- [ ] **Step 5: Write `evals/gap.py`**

```python
"""The CSF 2.0 gap-check eval (CSF spec 8), pack gap-dev: the dev company's 22 documents plus the gap extension's
(data/dev/gap), the workspace's built-in CSF questionnaire for the core, every Checked outcome through
answer_item, the Ask-me outcomes answered from evals/fixtures/gap-dev-answers.json (one left unanswered), scored
against data/dev/key/csf-core.yaml. `python -m evals.run --pack gap-dev` lands here."""

import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import ItemResult
from app.db.models import Document, Item, Workspace
from app.db.session import get_engine
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.ingest.store import ingest_document, store_statement
from app.llm.client import LLMClient
from app.stance import PROMPT_VERSION as STANCE_PROMPT
from datakit import csf as csf_data
from datakit import gap as gap_data
from datakit.schemas import Facts, GapFacts, Key, KeyItem, load_yaml
from evals import pack as packs
from evals import score

NAME = "gap-dev"
ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "evals" / "fixtures" / "gap-dev-answers.json"
STATEMENT_DATE = date(2026, 10, 5)  # fixed, so stored statements never change with the clock
SECRETS = ("sk9Kestrel2026xQ",)  # the API key in the fixture's supply-chain answer
GATES: dict[str, tuple[str, float]] = {
    "cited_coverage": (">=", 1.0),
    "trap_coverage": ("<=", 0.0),
    "label_accuracy": (">=", 0.80),
    "disagreements_caught": (">=", 1.0),
    "stated_noncompliance": (">=", 1.0),
    "nist_text_intact": (">=", 1.0),
    "honest_tiers": (">=", 1.0),
    "redaction_private_leaks": ("<=", 0.0),
}


def always(step: str) -> bool:
    """Evals measure the engine, not the budget."""
    return True


@dataclass(frozen=True)
class GapPack:
    dev: packs.Pack
    gap: GapFacts
    facts: Facts  # the dev fact sheet merged with the gap extension
    control: dict[str, str]  # Checked CSF id -> fact-sheet control
    keys: dict[str, KeyItem]  # Checked CSF id -> key entry


@dataclass
class GapObserved:
    results: dict[str, ItemResult]  # Checked CSF id -> what the engine produced
    labels: dict[str, str | None]  # every CSF id -> the gap label shown (None: no label)
    items: list[str]  # CSF ids of the built-in questionnaire's items, in order
    statements: dict[str, str]  # answered Ask-me CSF id -> stored statement documents.id
    kinds: dict[str, str]  # statement documents.id -> kind as stored
    doc_ids: dict[str, str]  # fact-sheet document id -> documents.id
    stored: dict[str, list[str]]  # documents.id -> stored lines
    leaks: int  # private strings found in stored statements or in model requests
    private: int  # private strings planted in the Ask-me answers


def load() -> GapPack:
    facts, gap = gap_data.load("dev")
    key = load_yaml(ROOT / "data" / "dev" / "key" / f"{gap_data.NAME}.yaml", Key)
    return GapPack(
        packs.load("dev"),
        gap,
        gap_data.merged(facts, gap),
        {m.csf_id: m.control for m in gap.outcomes},
        {k.code: k for k in key.items},
    )


def run(llm: LLMClient, models: dict[str, str]) -> dict[str, Any]:
    from evals.run import Log, _leaks, _stored  # evals.run imports this module

    pack = load()
    fw = csf.framework()
    answers: dict[str, str] = json.loads(ANSWERS.read_text(encoding="utf-8"))
    log = Log(llm)
    with Session(get_engine()) as session:
        ws = Workspace()
        session.add(ws)
        session.commit()
        try:
            doc_ids: dict[str, str] = {}
            for spec in pack.facts.documents:  # the dev sheet's order, then the extension's
                doc = ingest_document(
                    session,
                    ws.id,
                    spec.filename,
                    gap_data.doc_path("dev", pack.gap, spec).read_bytes(),
                    source="sample",
                    llm=log,
                    model=models["classify"],
                    spend=always,
                )
                doc_ids[spec.id] = str(doc.id)
            q = csf.questionnaire_for(session, ws.id, "core")
            items = [
                x
                for x in session.scalars(
                    select(Item.csf_id).where(Item.questionnaire_id == q.id).order_by(Item.position)
                )
                if x is not None
            ]
            session.commit()
            results: dict[str, ItemResult] = {}
            statements: dict[str, str] = {}
            labels: dict[str, str | None] = {}
            for csf_id in items:
                o = fw.get(csf_id)
                result = csf.check_outcome(session, ws.id, o, log, models, always)
                if result is not None:
                    results[o.id] = result
                    labels[o.id] = csf.gap_label(o, result.decision.label, result.decision.value)
                elif o.id in answers:
                    doc = store_statement(
                        session, ws.id, answers[o.id], filename=f"answer-{o.id}.txt", today=STATEMENT_DATE
                    )
                    statements[o.id] = str(doc.id)
                    labels[o.id] = csf.gap_label(o, "user_confirmed", None, doc.id)
                else:
                    labels[o.id] = csf.gap_label(o, None)
            for o in fw.outcomes:
                labels.setdefault(o.id, csf.gap_label(o, None))
            stored = _stored(session, ws.id)
            kinds = {sid: session.get_one(Document, uuid.UUID(sid)).kind for sid in statements.values()}
        finally:
            session.execute(delete(Workspace).where(Workspace.id == ws.id))
            session.commit()
    # sample documents name people legitimately; the visitor's answers must reach neither storage nor a model
    private = [s for s in (*pack.dev.private_strings(), *SECRETS) if any(s in a for a in answers.values())]
    leaks = _leaks(private, [x for sid in statements.values() for x in stored.get(sid, [])])
    leaks += _leaks(SECRETS, [r.user for r in log.requests])
    obs = GapObserved(results, labels, items, statements, kinds, doc_ids, stored, leaks, len(private))
    metrics = score_gap(pack, obs)
    return {
        "pack": NAME,
        "models": {k: models[k] for k in ("stance", "draft")},  # the only steps this pack calls
        "prompts": [STANCE_PROMPT, DRAFT_PROMPT],
        "metrics": metrics,
        "gates": score.gates(metrics, GATES),
        "label_misses": misses(pack, obs),
        "items": {
            code: {
                "label": labels[code],
                "decide": r.decision.label,
                "value": r.decision.value,
                "citations": len(r.decision.citations),
                "dropped": sorted(d.reason for d in r.decision.dropped),
                "draft": r.draft.source,
            }
            for code, r in sorted(results.items())
        },
    }


def _expected(pack: GapPack) -> dict[str, str | None]:
    fw = csf.framework()
    return {c: csf.gap_label(fw.get(c), k.expected_label, k.expected_value) for c, k in pack.keys.items()}


def _got(pack: GapPack, obs: GapObserved) -> dict[str, str | None]:
    fw = csf.framework()
    return {
        c: csf.gap_label(fw.get(c), obs.results[c].decision.label, obs.results[c].decision.value)
        for c in pack.keys
    }


def score_gap(pack: GapPack, obs: GapObserved) -> dict[str, float | None]:
    if missing := sorted(set(pack.keys) - set(obs.results)):  # a key with no result must fail loudly
        raise ValueError(f"no result for Checked outcomes: {', '.join(missing)}")
    m: dict[str, float | None] = {}
    want, got = _expected(pack), _got(pack, obs)
    shown = [obs.results[c].decision for c in pack.keys if got[c] in ("covered", "partly_covered")]
    m["cited_coverage"] = score._gated(*score._citation_counts(shown, obs.stored))
    specs = {d.id: d for d in pack.facts.documents}
    fact_doc = {v: k for k, v in obs.doc_ids.items()}
    traps = [c for c in pack.keys if gap_data.trap_sources(pack.facts, pack.control[c])]
    bad = sum(got[c] == "covered" for c in traps)
    bad += sum(not specs[fact_doc[x.document_id]].evidence_allowed for d in shown for x in d.citations)
    m["trap_coverage"] = score._count(bad, len(traps))
    m["label_accuracy"] = score._gated(sum(got[c] == want[c] for c in pack.keys), len(pack.keys))
    for name, label in (("disagreements_caught", "documents_disagree"), ("stated_noncompliance", "not_met")):
        planted = [c for c in pack.keys if want[c] == label]
        m[name] = score._gated(sum(got[c] == label for c in planted), len(planted))
    m["nist_text_intact"] = 0.0 if csf_data.check() else 1.0
    honest = cases = 0
    for o in csf.framework().outcomes:
        if o.tier == "not_checked":
            cases += 1
            honest += o.id not in obs.items and o.id not in obs.results and obs.labels.get(o.id) is None
        elif o.tier == "ask":
            cases += 1
            sid = obs.statements.get(o.id)
            shows = "confirmed_by_you" if sid is not None else "not_answered"
            honest += (
                obs.labels.get(o.id) == shows
                and o.id not in obs.results
                and (sid is None or obs.kinds.get(sid) == "statement")
            )
    m["honest_tiers"] = score._gated(honest, cases)
    m["redaction_private_leaks"] = score._count(obs.leaks, obs.private)
    recalls = [
        sum(score._found(obs.results[c], obs.doc_ids[e.doc], e.quote) is not None for e in k.evidence)
        / len(k.evidence)
        for c, k in pack.keys.items()
        if k.evidence
    ]
    m["retrieval_recall_at_8"] = round(statistics.fmean(recalls), 4) if recalls else None
    m["cost_usd_per_core_run"] = round(sum(r.cost_usd for r in obs.results.values()), 4)
    m["seconds_per_core_run"] = round(sum(r.latency_ms for r in obs.results.values()) / 1000, 2)
    return m


def misses(pack: GapPack, obs: GapObserved) -> list[str]:
    want, got = _expected(pack), _got(pack, obs)
    return [f"{c}: expected {want[c]}, got {got[c]}" for c in sorted(pack.keys) if want[c] != got[c]]
```

- [ ] **Step 6: `evals/run.py`: dispatch and output names**

In `main`, replace `report = run(args.pack, log, models)` inside the `try` with:

```python
        if args.pack == "gap-dev":
            from evals import gap  # imported here: evals.gap imports this module

            report = gap.run(log, models)
        else:
            report = run(args.pack, log, models)
```

and replace the two `write_text` lines with:

```python
    stem = "gap-dev" if args.pack == "gap-dev" else "latest"  # each pack keeps its own committed results
    (RESULTS / f"{stem}.json").write_text(json.dumps(jsonable(report), indent=2, sort_keys=True) + "\n")
    (RESULTS / f"{stem}.md").write_text(score.markdown(report))
```

Update the module docstring's usage block with `python -m evals.run --pack gap-dev   # the CSF gap check (evals/gap.py)`.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_eval_gap.py tests/test_eval_run.py tests/test_eval_score.py -q && mypy app scripts datakit evals`
Expected: PASS; `Success: no issues found`.

- [ ] **Step 8: Check that replay refuses to run without recordings**

Run: `python -m evals.run --pack gap-dev; echo "exit $?"`
Expected: `recording missing (...); re-record with --mode record` and `exit 2`.

- [ ] **Step 9: Commit**

```bash
git add evals/gap.py evals/fixtures/gap-dev-answers.json evals/run.py evals/score.py tests/test_eval_gap.py
git commit -m "feat(evals): gap-dev pack with fail-closed CSF gates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Then: adversary checkpoint (Fable 5.1)** on `main..plan6a` (see Review gates). Its fixes land, each with a test, before Task 7.

---

### Task 7: Record, baseline, gates in CI, docs (the lead)

Run by the lead on `plan6a` in `~/Desktop/portfolio/projects/VART-wt-csf`, following plan2c Task 4. The recording uses the eval key and needs no approval up to its $5 cap; the first baseline needs Tarun's approval (CSF spec 11).

**Files:**
- Create (by the record run): `evals/recorded/gap-dev.jsonl`, `evals/results/gap-dev.json`, `evals/results/gap-dev.md`
- Modify: `evals/gap.py` (`GATES`, Step 5), `.github/workflows/ci.yml`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/CONTRACTS.md` (with the lead's OK), `docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md`
- Possibly modify (tuning, Step 4 only): `data/csf/tiers.yaml` and `data/csf/csf-2.0.json` (question phrasings), `data/dev/gap/facts.yaml` and `data/dev/key/csf-core.yaml` (a fact-sheet correction)

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: the committed gap-dev baseline that replays byte for byte; CI that replays it and fails on a gate or on drift.

- [ ] **Step 1: The recording (lead, eval key)**

```bash
cd ~/Desktop/portfolio/projects/VART-wt-csf && source ~/Desktop/portfolio/projects/VART-wt-csf/.venv/bin/activate
(cd ~/Desktop/portfolio/projects/VART && docker compose exec db createdb -U vart vart_test_record 2>/dev/null; true)
export DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_record
alembic upgrade head
(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack gap-dev --mode record)
```

Expected: about 58 model calls (a stance and a draft per Checked outcome with passages; none for Ask-me or not-checked), cents, a few minutes; the last line reads `N/8 gates pass`. A failed stance call stops the run; running it again resumes from the recordings already made. A stance reply that does not parse is recorded before it is rejected: delete that row from `evals/recorded/gap-dev.jsonl` or re-run with `--refresh stance`.

- [ ] **Step 2: Commit the recordings and results**

```bash
git add evals/recorded/gap-dev.jsonl evals/results/gap-dev.json evals/results/gap-dev.md
git commit -m "evals: first gap-dev recordings and baseline" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Replay check (no key)**

Run: `python -m evals.run --pack gap-dev; echo "exit $?"; python -m evals.run --pack dev; git diff --exit-code evals/results && git status --short evals/`
Expected: the same gate line and exit code as the record run; the dev pack's line unchanged; no diff. A diff means something is not deterministic: fix the cause and re-record; never commit a replay that differs from its recording.

- [ ] **Step 4: If a gate fails, tune within these rules (at most three rounds)**

Read `evals/results/gap-dev.md` (label misses) and `gap-dev.json` (`items`: gap label, decide label, citations, dropped reasons). Sort each miss into retrieval (the key quote never reached the eight passages; `retrieval_recall_at_8`), stance, or the fact sheet. Allowed: rewording a question in `data/csf/tiers.yaml` as a generic paraphrase of NIST's outcome (then `python -m datakit.csf build && python -m datakit.gap dev`); a fact-sheet correction when a document really says something about an outcome's control that the sheet did not register (register the statement in `data/dev/gap/facts.yaml` under that control, re-derive, and say so in the report: the key follows the documents, never the engine); the engine changes plan2c Task 4 Step 7 allows, each re-recording both packs. Not allowed: editing `csf-core.yaml` by hand, a question that names a document or quotes it, item-specific rules, a lowered gate. Every change carries a test where code changes, goes through review, and is followed by Steps 1-3 again. The same gate failing after two rounds triggers adversary checkpoint 2; after three rounds, Tarun decides.

- [ ] **Step 5: Tarun approves the baseline; tighten the gates**

Send Tarun the gate table from `evals/results/gap-dev.md` with the label misses, `cost_usd_per_core_run`, `seconds_per_core_run` and `retrieval_recall_at_8`. On his approval, tighten `label_accuracy` in `evals/gap.GATES` to max(0.80, baseline - 0.02) rounded down to two decimals (the other gates are already 1.0 or 0). Run: `python -m evals.run --pack gap-dev; echo "exit $?"` (expected `8/8 gates pass`, `exit 0`, only the target changed in `git diff evals/results`), then:

```bash
git add evals/gap.py evals/results/gap-dev.json evals/results/gap-dev.md
git commit -m "evals: gap-dev gates tightened from the approved baseline" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Wire CI and update the docs**

`.github/workflows/ci.yml`, backend job: after `- run: python -m evals.run --pack dev` add `- run: python -m evals.run --pack gap-dev` (the existing `git diff --exit-code evals/results` that follows covers both packs; `python -m datakit.validate all` already runs the `csf` and `gap` stages). Run the job's commands locally in order on `vart_test_csf`; all must pass.

`CLAUDE.md` map: in the Engine line add `app/csf.py` (CSF 2.0 gap check: framework, built-in questionnaire, gap labels); add a line `data/csf/` (NIST CSF 2.0 extract, `tiers.yaml`, built `csf-2.0.json`; `python -m datakit.csf build`) and `data/dev/gap/` (the gap check's fact-sheet extension; `python -m datakit.gap dev`); in `evals/` add `gap.py` (the `gap-dev` pack) and in Commands `python -m evals.run --pack gap-dev`.

`docs/CONTRACTS.md` (lead's OK, rule 10): add a row `| csf | app/csf.py (6A) | framework() -> Framework; in_scope(scope) -> tuple[Outcome, ...]; item_input(o) -> ItemInput; gap_label(o, label, value=None, statement_id=None) -> GapLabel or None; questionnaire_for(session, workspace_id, scope) -> Questionnaire; check_outcome(session, workspace_id, o, llm, models, spend) -> ItemResult or None; ask_queue(outcomes, asked) -> list[QueueEntry] | via answer_item |` and a change-log line `- <date>: csf unit added (Plan 6A); no existing signature changed.`

`docs/PROGRESS.md`: an at-a-glance row `6A CSF gap check, backend and evals | done | gap-dev baseline <label accuracy>; 6B (view, export, README, E2E) after Plan 3`, and decision rows dated the merge day for execution-note decisions 1-6 and "The gap check's planted cases live in a gap-only extension of the dev pack (data/dev/gap), so the questionnaire eval is unchanged".

Spec sync (`2026-10-05-vart-csf-gap-check-design.md`), one sentence each: section 4 (version, date and source stored once at the top of the file; SP 800-53 Rev 5.2.0; `source_url` is the Reference Tool page; the change log is in `tiers.yaml`), the exact tiers (29 / 5 / 72), section 5.3 (`na` shows no label; a confirmed Checked outcome shows Confirmed by you), section 5.4 (Questions for you holds Ask-me outcomes only), section 8 (the gap extension and its planted cases; gate names as in `evals/gap.py`; cost and seconds per core run reported).

```bash
git add .github/workflows/ci.yml CLAUDE.md docs/PROGRESS.md docs/CONTRACTS.md docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md
git commit -m "docs, ci: gap-dev replayed in CI; CSF gap check in the map, contracts, progress and spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Final review and release plan**

The final Opus review of `main..plan6a`. On a clean review the lead sends Tarun the release plan: (1) push `plan6a` and open a pull request to `main`; (2) wait for green CI; (3) Tarun runs `ops/setup.sh migrate` from the branch head (Task 2's migration reaches Neon before `main` moves); (4) fast-forward `main` and push. No visitor-facing change ships until 6B. Push and release only on his OK.

## Self-review notes (for the lead)

- **Spec coverage.** Section 4: Task 1 (file, fields, verbatim NIST text, drift test, refresh rule, tiers fixed with Tarun). Section 5: steps 2-5 in Tasks 3-4 (`check_outcome`, gap labels, `ask_queue` + `store_statement`, not-checked makes no call); step 1 (the view starting a run, caps, expiry) and step 6 (re-check after an upload or answer) are HTTP flows, deferred to 6B with Plan 3's runner (`recheck` is reused unchanged). Section 6: Tasks 2 and 4. Section 7: 6B. Section 8: Tasks 5-7, every gate in the table (cost and speed reported), fail-closed, CI replay, eval key. Section 9: Ask-me answers redacted by `store_statement` and measured by the redaction gate; the CSF file is read, never fetched or executed. Section 11: Tarun's approvals of the IDs (Task 1 Step 7) and of the first baseline (Task 7 Step 5); README and view are 6B.
- **Type consistency.** `gap_label(o, label, value=None, statement_id=None)` is called the same way in Tasks 3, 4, 5 and 6; `questionnaire_for`, `check_outcome`, `ask_queue`, `item_input` keep Task 4's signatures in Task 6; `datakit.gap.doc_path(pack, gap, spec)` and `trap_sources(f, control)` match their uses in `evals/gap.py`; `score.gates(metrics, table)` is the one signature change in `evals/score.py`.
- **Counts that tests pin and that move together:** 106 outcomes, 29 Checked, 5 Ask-me, 72 not checked, 34 in the core, 7 in Govern, 17 expected Covered. If Tarun changes the tiers at the review gate, update these numbers in `tests/datakit/test_csf.py`, `tests/test_csf.py`, `tests/datakit/test_gap.py` and `tests/test_eval_gap.py` together with the outcome map.
