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
- "What the visitor sees as 'the framework' is always NIST's verbatim `outcome` text. Only `tier`, `question` and `parts` are VART's." (Task 8 amended spec 4: `parts` is the outcome cut by a fixed rule.) (CSF spec 4)
- "Refreshing the file is a deliberate change with a new `retrieved` date, a re-run of the eval and a change-log line." (CSF spec 4) The change log is the comment block at the top of `data/csf/tiers.yaml`.
- Decide does not change (CSF spec 5.3): gap labels are computed from `Decision.label` and `Decision.value` only. `app/decide.py`, `app/text.py`, `app/patterns.py`, `app/contracts.py` and the signatures in `docs/CONTRACTS.md` are not edited by any task; no frozen signature needs to change. Adding a new row for `app/csf.py` to `docs/CONTRACTS.md` (Task 7) needs the lead's OK and a change-log line (CLAUDE.md rule 10).
- Engine code spends the budget before every model call and holds no database transaction across one (CLAUDE.md rule 11): `check_outcome` reaches a model only through `answer_retrieved`, once per part (`check_parts`), with each part's draft refused before anything is spent (Task 8); Ask-me and not-checked outcomes make no model call (CSF spec 5.4-5.5).
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
    assert len(labels) == 31 and set(labels) == {o.id for o in gap.checked()}
    by_label: dict[str | None, set[str]] = {}
    for code, label in labels.items():
        by_label.setdefault(label, set()).add(code)
    assert by_label["documents_disagree"] == {"PR.AA-05", "DE.AE-06"}
    assert by_label["not_met"] == {"ID.RA-02", "DE.AE-07"}
    assert by_label["gap"] == {"ID.AM-03", "PR.AA-06", "PR.IR-04"}
    assert by_label["partly_covered"] == {
        "PR.AA-03", "RS.MA-01", "RS.CO-02", "PR.DS-02", "PR.DS-11", "PR.IR-03",
        "ID.AM-05", "ID.AM-08", "GV.PO-02", "PR.AA-01", "PR.PS-02", "PR.PS-06",
    }  # final key (Task 7, judges 1 and 2); the tests/datakit/test_gap.py copy is the live one
    assert Counter(labels.values())["covered"] == 12


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

Expected: 73 stance requests (72 live calls: GV.PO-02 part 3 replays GV.PO-01 part 2's recording) and no draft calls, cents, a few minutes; the last line reads `N/8 gates pass`. A failed stance call stops the run; running it again resumes from the recordings already made. A stance reply that does not parse is recorded before it is rejected: delete that row from `evals/recorded/gap-dev.jsonl` or re-run with `--refresh stance`.

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

`docs/CONTRACTS.md` (lead's OK, rule 10): add a row `| csf | app/csf.py (6A) | framework() -> Framework; in_scope(scope) -> tuple[Outcome, ...]; item_input(o) -> ItemInput; gap_label(o, label, value=None, statement_id=None) -> GapLabel or None; questionnaire_for(session, workspace_id, scope) -> Questionnaire; check_outcome(session, workspace_id, o, llm, models, spend) -> ItemResult or None; ask_queue(outcomes, asked) -> list[QueueEntry]; part_inputs(o) -> tuple[ItemInput, ...]; part_label(r) -> PartLabel; combine(labels) -> PartLabel; explain(o, parts) -> str; aggregate(o, parts) -> ItemResult; check_parts(session, workspace_id, o, llm, models, spend) -> list[ItemResult]; evidence(session, workspace_id, item) -> Retrieval | via answer_retrieved per part |` and a change-log line `- <date>: csf unit added (Plan 6A); no existing signature changed.`

`docs/PROGRESS.md`: an at-a-glance row `6A CSF gap check, backend and evals | done | gap-dev baseline <label accuracy>; 6B (view, export, README, E2E) after Plan 3`, and decision rows dated the merge day for execution-note decisions 1-6 and "The gap check's planted cases live in a gap-only extension of the dev pack (data/dev/gap), so the questionnaire eval is unchanged".

Spec sync (`2026-10-05-vart-csf-gap-check-design.md`), one sentence each: section 4 (version, date and source stored once at the top of the file; SP 800-53 Rev 5.2.0; `source_url` is the Reference Tool page; the change log is in `tiers.yaml`), the exact tiers (29 / 5 / 72), section 5.3 (`na` shows no label; a confirmed Checked outcome shows Confirmed by you), section 5.4 (Questions for you holds Ask-me outcomes only), section 8 (the gap extension and its planted cases; gate names as in `evals/gap.py`; cost and seconds per core run reported).

```bash
git add .github/workflows/ci.yml CLAUDE.md docs/PROGRESS.md docs/CONTRACTS.md docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md
git commit -m "docs, ci: gap-dev replayed in CI; CSF gap check in the map, contracts, progress and spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Final review and release plan**

The final Opus review of `main..plan6a`. On a clean review the lead sends Tarun the release plan: (1) push `plan6a` and open a pull request to `main`; (2) wait for green CI; (3) Tarun runs `ops/setup.sh migrate` from the branch head (Task 2's migration reaches Neon before `main` moves); (4) fast-forward `main` and push. No visitor-facing change ships until 6B. Push and release only on his OK.

### Task 8: Per-part questions

**Review Focus**
1. **Precedence and the explanation.** Documents disagree beats Not met (stated), which beats Covered, then Gap,
   then Partly covered. The explanation quotes only the parts that decided the label, each with its own stance, so a
   "No." never sits over yes lines (adversary C2). Pinned by the table test, the exhaustive test over every mix of
   up to three parts, and the A/B/C test.
2. **Citations (`ck_answers_cited`).** No Covered, Partly covered, Not met or Documents disagree outcome is left
   without a citation, and a Gap outcome cites nothing. The citations are the parts' union, deduplicated with stance
   in the key, and each keeps its own part's stance. The outcome's Decision is a display record. Pinned exhaustively.
3. **The cut and the wording.** The cut is mechanical and uses NIST's text only (spec 4, amended): every listed verb
   is a part; in a sentence with one verb, a comma list of three or more nouns is a part per noun wherever it
   stands, inside a qualifier too (Ruling 19); pairs are never cut, and a qualifier is never a part of its own and
   stays on the verb it follows. The csf stage fails on any added word that is not in an example
   clause, is not mapped to a NIST word, or would make more than three on its outcome, and on any dropped NIST word.
   The reviewer checks the 73-row table in Step 2 against the rule.
4. **Hard rule 11, part by part.** Each part spends the budget before its stance call. No part spends on a draft or
   calls one. No transaction is open during any part's model call. A refused budget stops the outcome after the
   parts it paid for. Pinned in `tests/test_csf_parts.py`.
5. **The key is independent and visible.** Expected labels stay at the outcome level, from judge 2 and its per-part
   re-judge of PR.DS-01 and PR.DS-02: 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree, 3 Gap. PR.DS-11
   keeps its Partly covered override; its interval disagreement cannot be planted (C1). PR.DS-02 is Partly covered
   because availability in transit has no line. Every override names `missing_parts`, and `part_agreement` is reported
   without being a gate. The key is never computed through `combine`. The dev pack replays 15/15 with no diff.

**Where it runs.** After tune round 1 (61484b2) and before Task 7 Step 5. Tarun chose option A on 2026-10-06.
Rulings 15, 17, 18 and 19 govern it. Ruling 17 accepts adversary checkpoint 2 in full. Ruling 19 settles the
recheck: the per-part re-judge of PR.DS-01 and PR.DS-02 is already done (`gap-key-judge-2.md`, "Re-judge per part")
and is folded into Step 10, so no step here runs a judge. The tuning count restarts at no more than 2 rounds, then Tarun decides (Ruling 16). Step 1 and Steps 13-14
belong to the lead; the implementer runs Steps 2-12.

**Reviewer:** Opus (the aggregation and the key).

**Files:**
- Modify:
  - `data/csf/tiers.yaml`: `parts`, `paraphrase_words`, ID.AM-08's question (Ruling 14), and change-log lines
  - `data/csf/csf-2.0.json`: rebuilt
  - `datakit/csf.py`, `tests/datakit/test_csf.py`
  - `datakit/schemas.py`: `GapOutcome.missing_parts`
  - `datakit/gap.py`, `tests/datakit/test_gap.py`
  - `data/dev/gap/facts.yaml`
  - `data/dev/key/csf-core.yaml`: re-derived, never edited by hand
  - `app/csf.py`, `tests/test_csf_framework.py`
  - `evals/gap.py`, `tests/test_eval_gap.py`
- Create: `tests/test_csf_parts.py`
- Lead only:
  - the CSF spec and this plan's text (Step 1)
  - the 6B carries in `progress.md` (Step 1)
  - `evals/recorded/gap-dev.jsonl` and `evals/results/gap-dev.{json,md}` (Step 13)
- Not touched: `app/contracts.py`, `docs/CONTRACTS.md`, `app/decide.py`, `app/stance.py`, `app/draft.py`,
  `app/pipeline.py`, `app/retrieve.py`, `app/interview.py`, `app/text.py`, `app/patterns.py`,
  `app/services/llm_budget.py`, and all of the dev pack

**Interfaces:**
- Consumes:
  - `app.pipeline.answer_retrieved(session, workspace_id, item, retrieval, llm, models, spend) -> ItemResult` (unchanged)
  - `app.draft.template_answer(decision) -> str`
  - `app.decide.CONFIDENCE` and `app.decide.QUOTE_FAILURES`
  - `app.retrieve.retrieve(session, workspace_id, question, topic)`
  - `datakit.derive_key.is_usable_evidence`, `datakit.gap.derive_gap`
- Produces, in `app/csf.py`:
  - `PartLabel = Literal["covered", "partly_covered", "not_met", "documents_disagree", "gap"]` (`_CHECKED` now maps
    to it)
  - `Outcome.parts: tuple[str, ...] = ()`, its last field, non-empty exactly when `tier == "checked"` (checked at load)
  - `part_inputs(o) -> tuple[ItemInput, ...]`, with keys `"<id>#<n>"`
  - `part_label(r: ItemResult) -> PartLabel`
  - `combine(labels: Sequence[PartLabel]) -> PartLabel`
  - `explain(o, parts: Sequence[ItemResult]) -> str`
  - `aggregate(o, parts: Sequence[ItemResult]) -> ItemResult`
  - `check_parts(session, workspace_id, o, llm, models, spend) -> list[ItemResult]` (`[]` for Ask me; `ValueError`
    for not checked)
  - `PART_WORDS`, and `_DECIDE: dict[PartLabel, tuple[Label, Value | None]]`
  - `evidence(session, workspace_id, item: ItemInput) -> Retrieval` (its last argument was `o: Outcome`)
  - `check_outcome` keeps its signature and returns `aggregate(o, check_parts(...))`, or `None` for Ask me.
- Produces, in `datakit/csf.py`:
  - `FRAME`, `MAX_PARAPHRASE = 3`
  - `words(text) -> list[str]`, `added_words(part, nist) -> list[str]`
  - `build` writes `"parts"` on every outcome (`[]` unless checked)
  - `problems` names every bad part.
- Produces, elsewhere:
  - `datakit.schemas.GapOutcome.missing_parts: tuple[int, ...] = ()`
  - `datakit.gap.check` gains the override and conflict checks
  - `evals.gap`: `GapPack.missing_parts`, `GapObserved.parts`, the `part_agreement` metric (reported), and
    `items[<id>]["parts"]` and `["explanation"]` in `gap-dev.json`
- Frozen contracts: no change. Step 1 updates the text of the `csf` row that Task 7 Step 6 will add.

- [ ] **Step 1 (lead): apply the amendment, the plan edits and the 6B carries**

Apply `spec-amendment-parts.md` (revision 2) to the CSF spec. Then edit this plan:
- **Global Constraints**, the hard-rule-11 bullet: "`check_outcome` reaches a model only through
  `answer_retrieved`, once per part (`check_parts`), with each part's draft refused before anything is spent (Task
  8)".
- **Task 7 Step 1**: "73 stance requests (72 live calls: GV.PO-02 part 3 replays GV.PO-01 part 2's recording)
  and no draft calls".
- **Task 7 Step 6**, the `csf` row: add `part_inputs(o) -> tuple[ItemInput, ...]; part_label(r) -> PartLabel;
  combine(labels) -> PartLabel; explain(o, parts) -> str; aggregate(o, parts) -> ItemResult; check_parts(session,
  workspace_id, o, llm, models, spend) -> list[ItemResult]; evidence(session, workspace_id, item) -> Retrieval`,
  and change "via answer_item" to "via answer_retrieved per part".
- **Self-review notes**, the counts line: "106 outcomes, 31 Checked, 5 Ask-me, 70 not checked, 36 in the core, 7 in
  Govern, 73 parts; expected 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree, 3 Gap".

Add these 6B carries to `progress.md`:
- (a) Store each part's result as it lands, so a step refused by the hourly stance cap resumes without paying again
  for parts already done (spec 5.7, adversary I5).
- (b) The runner claims csf items until their parts add up to 8 or fewer per step (spec 5.7, I6).
- (c) Re-check per part: an open item per part key, and an accepted suggestion replaces that part's result before
  `combine` and `explain` run again (spec 5.6, I8).
- (d) The inspector shows each part's label, citations with their stance, and the document's status next to a
  draft-only quote (`check_parts`; minor M8).

Commit on the plan branch:

```bash
git add docs/superpowers/specs/2026-10-05-vart-csf-gap-check-design.md docs/superpowers/plans/2026-10-05-vart-csf-plan6a-backend.md
git commit -m "docs(csf): per-part questions (option A), spec amendment and Task 8" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the parts into `data/csf/tiers.yaml`**

The cut is spec 4's (amended) rule, applied to NIST's text only, the same for every outcome, with no exceptions:
1. Every listed verb is a part, and so is every listed gerund.
2. A sentence with one verb is cut at any comma list of three or more nouns, wherever it stands, inside a
   qualifier too. The rest of the qualifier stays on every part (Ruling 19).
3. A pair joined by "and" is never cut.
4. A qualifier is never a part of its own and stays on the verb it follows.
5. A second predicate is cut by the same rules.

The middle column of the table below quotes the NIST words each part comes from. A part may keep the example clause
the outcome's approved question had (Rulings 11a, 13 and 14): its words stand after "such as" or "for example" and
are mapped to the NIST word they are an instance of.

Two notes:
- PR.DS-01 and PR.DS-02 are cut into confidentiality, integrity and availability by rule 2. Judge 2 re-judged both
  per part (`gap-key-judge-2.md`, "Re-judge per part"). PR.DS-01 stays Covered, and Step 10 registers its integrity
  line. PR.DS-02 becomes Partly covered: no line protects availability in transit.
- ID.AM-05's four-noun list sits inside its "based on" qualifier. Rule 2 cuts it, so the outcome has four parts.
- GV.PO-02 part 3 is the same text as GV.PO-01 part 2, so the two share a recording key. That is harmless: same
  question, same passages, same stance (minor M3).

That gives 31 outcomes and 73 parts:

| Outcome | # | NIST clause, as written | Part |
|---|---|---|---|
| GV.PO-01 | 1 | is established based on organizational context, cybersecurity strategy, and priorities | Is the policy for managing cybersecurity risks established based on organizational context, cybersecurity strategy and priorities? |
|  | 2 | is communicated | Is the policy for managing cybersecurity risks communicated? |
|  | 3 | [is] enforced | Is the policy for managing cybersecurity risks enforced? |
| GV.PO-02 | 1 | is reviewed | Is the policy for managing cybersecurity risks reviewed? |
|  | 2 | updated | Is the policy for managing cybersecurity risks updated? |
|  | 3 | communicated | Is the policy for managing cybersecurity risks communicated? |
|  | 4 | and enforced to reflect changes in requirements, threats, technology, and organizational mission | Is the policy for managing cybersecurity risks enforced to reflect changes in requirements, threats, technology and organizational mission? |
| ID.AM-01 | 1 | Inventories of hardware ... are maintained | Are inventories of hardware managed by the organization maintained? |
| ID.AM-02 | 1 | software | Are inventories of software managed by the organization maintained? |
|  | 2 | services | Are inventories of services managed by the organization maintained? |
|  | 3 | and systems | Are inventories of systems managed by the organization maintained? |
| ID.AM-03 | 1 | Representations of ... authorized network communication and internal and external network data flows are maintained | Are representations of the organization's authorized network communication and internal and external network data flows maintained? |
| ID.AM-05 | 1 | prioritized based on classification | Are assets prioritized based on classification? |
|  | 2 | criticality | Are assets prioritized based on criticality? |
|  | 3 | resources | Are assets prioritized based on resources? |
|  | 4 | and impact on the mission | Are assets prioritized based on impact on the mission? |
| ID.AM-08 | 1 | Systems | Are systems managed throughout their life cycles, for example from acquisition to retirement? |
|  | 2 | hardware | Is hardware managed throughout its life cycle, for example from acquisition to retirement? |
|  | 3 | software | Is software managed throughout its life cycle, for example from acquisition to retirement? |
|  | 4 | services | Are services managed throughout their life cycles, for example from acquisition to retirement? |
|  | 5 | and data | Is data managed throughout its life cycle, for example from acquisition to retirement? |
| ID.RA-01 | 1 | identified | Are vulnerabilities in assets identified? |
|  | 2 | validated | Are vulnerabilities in assets validated? |
|  | 3 | and recorded | Are vulnerabilities in assets recorded? |
| ID.RA-02 | 1 | Cyber threat intelligence is received from information sharing forums and sources | Is cyber threat intelligence received from information sharing forums and sources? |
| ID.RA-08 | 1 | Processes for receiving | Are processes for receiving vulnerability disclosures established? |
|  | 2 | analyzing | Are processes for analyzing vulnerability disclosures established? |
|  | 3 | and responding to vulnerability disclosures are established | Are processes for responding to vulnerability disclosures established? |
| PR.AA-01 | 1 | authorized users | Are identities and credentials for authorized users managed by the organization? |
|  | 2 | services | Are identities and credentials for services managed by the organization? |
|  | 3 | and hardware | Are identities and credentials for hardware managed by the organization? |
| PR.AA-03 | 1 | Users | Are users authenticated? |
|  | 2 | services | Are services authenticated? |
|  | 3 | and hardware | Is hardware authenticated? |
| PR.AA-05 | 1 | are defined in a policy | Are access permissions, entitlements and authorizations defined in a policy? |
|  | 2 | managed | Are access permissions, entitlements and authorizations managed? |
|  | 3 | enforced | Are access permissions, entitlements and authorizations enforced? |
|  | 4 | and reviewed | Are access permissions, entitlements and authorizations reviewed? |
|  | 5 | and incorporate the principles of least privilege and separation of duties | Do access permissions, entitlements and authorizations incorporate the principles of least privilege and separation of duties? |
| PR.AA-06 | 1 | managed | Is physical access to assets managed? |
|  | 2 | monitored | Is physical access to assets monitored? |
|  | 3 | and enforced commensurate with risk | Is physical access to assets enforced commensurate with risk? |
| PR.DS-01 | 1 | The confidentiality | Is the confidentiality of data at rest protected, for example by encryption? |
|  | 2 | integrity | Is the integrity of data at rest protected? |
|  | 3 | and availability of data-at-rest are protected | Is the availability of data at rest protected? |
| PR.DS-02 | 1 | The confidentiality | Is the confidentiality of data in transit protected, for example by encryption? |
|  | 2 | integrity | Is the integrity of data in transit protected? |
|  | 3 | and availability of data-in-transit are protected | Is the availability of data in transit protected? |
| PR.DS-11 | 1 | created | Are backups of data created? |
|  | 2 | protected | Are backups of data protected? |
|  | 3 | maintained | Are backups of data maintained? |
|  | 4 | and tested | Are backups of data tested? |
| PR.PS-01 | 1 | established | Are configuration management practices, such as baseline configurations and change control, established? |
|  | 2 | and applied | Are configuration management practices, such as baseline configurations and change control, applied? |
| PR.PS-02 | 1 | maintained | Is software maintained? |
|  | 2 | replaced | Is software replaced? |
|  | 3 | and removed commensurate with risk | Is software removed commensurate with risk? |
| PR.PS-04 | 1 | Log records are generated | Are log records generated? |
|  | 2 | and made available for continuous monitoring | Are log records made available for continuous monitoring, for example centrally? |
| PR.PS-06 | 1 | practices are integrated | Are secure software development practices, such as security testing and code review, integrated? |
|  | 2 | and their performance is monitored throughout the software development life cycle | Is the performance of secure software development practices monitored throughout the software development life cycle? |
| PR.IR-03 | 1 | Mechanisms are implemented to achieve resilience requirements in normal and adverse situations | Are mechanisms implemented to achieve resilience requirements, such as recovery objectives, in normal and adverse situations? |
| PR.IR-04 | 1 | Adequate resource capacity to ensure availability is maintained | Is adequate resource capacity to ensure availability maintained? |
| DE.CM-09 | 1 | Computing hardware and software | Are computing hardware and software monitored to find potentially adverse events? |
|  | 2 | runtime environments | Are runtime environments monitored to find potentially adverse events? |
|  | 3 | and their data are monitored to find potentially adverse events | Is the data of computing hardware, software and runtime environments monitored to find potentially adverse events? |
| DE.AE-06 | 1 | Information on adverse events is provided to authorized staff and tools | Is information on adverse events provided to authorized staff and tools, for example through alerts? |
| DE.AE-07 | 1 | Cyber threat intelligence and other contextual information are integrated into the analysis | Are cyber threat intelligence and other contextual information integrated into the analysis of adverse events? |
| RS.MA-01 | 1 | The incident response plan is executed in coordination with relevant third parties once an incident is declared | Is the incident response plan executed in coordination with relevant third parties once an incident is declared? |
| RS.AN-03 | 1 | Analysis is performed to establish what has taken place during an incident and the root cause of the incident | Is analysis performed to establish what has taken place during an incident and the root cause of the incident? |
| RS.CO-02 | 1 | Internal and external stakeholders are notified of incidents | Are internal and external stakeholders, such as customers, notified of incidents? |
| RS.MI-01 | 1 | Incidents are contained | Are incidents contained? |
| RC.RP-01 | 1 | The recovery portion of the incident response plan is executed once initiated from the incident response process | Is the recovery portion of the incident response plan, such as disaster recovery failover and restore, executed once initiated from the incident response process? |

In `data/csf/tiers.yaml`:
- Replace ID.AM-08's question (Ruling 14) with
  `"Are systems, hardware, software, services and data managed throughout their life cycles, from acquisition to retirement?"`.
- In the header comment, change "a data change plus a control in data/dev/gap/facts.yaml" to "a data change (its
  question and parts) plus a control in data/dev/gap/facts.yaml".
- Add these change-log lines:

```yaml
#   2026-10-06  Ruling 14: ID.AM-08's question drops "including secure disposal" (not NIST's): "..., from acquisition to retirement".
#   2026-10-06  option A (Tarun; CSF spec 4 and 5.2-5.3 amended; Rulings 15, 17): parts for every checked outcome (73), cut by
#               spec 4's rule; paraphrase_words. Parts are frozen from the first recording: every later change is a tuning
#               round with a line here citing NIST's clause.
```

Then append at the end:

```yaml
# Parts (CSF spec 4 and 5.2, amended 2026-10-06): each checked outcome cut by spec 4's rule (every listed verb; in a
# one-verb sentence, a comma list of three or more nouns wherever it stands; pairs never cut; a qualifier is never
# its own part and stays on its verb),
# as yes/no questions in NIST's order. Each part runs through the pipeline on its own; app.csf.combine labels the
# outcome. A part uses NIST's words for its outcome (outcome and category text) and question words
# (datakit.csf.FRAME); any other word stands in an example clause ("such as", "for example") and is listed under
# paraphrase_words, mapped to the NIST word it is an instance of (at most 3 per outcome). Every word of NIST's
# outcome is in at least one part. python -m datakit.validate csf checks all of it.
parts:
  GV.PO-01:
    - "Is the policy for managing cybersecurity risks established based on organizational context, cybersecurity strategy and priorities?"
    - "Is the policy for managing cybersecurity risks communicated?"
    - "Is the policy for managing cybersecurity risks enforced?"
  GV.PO-02:
    - "Is the policy for managing cybersecurity risks reviewed?"
    - "Is the policy for managing cybersecurity risks updated?"
    - "Is the policy for managing cybersecurity risks communicated?"
    - "Is the policy for managing cybersecurity risks enforced to reflect changes in requirements, threats, technology and organizational mission?"
  ID.AM-01:
    - "Are inventories of hardware managed by the organization maintained?"
  ID.AM-02:
    - "Are inventories of software managed by the organization maintained?"
    - "Are inventories of services managed by the organization maintained?"
    - "Are inventories of systems managed by the organization maintained?"
  ID.AM-03:
    - "Are representations of the organization's authorized network communication and internal and external network data flows maintained?"
  ID.AM-05:
    - "Are assets prioritized based on classification?"
    - "Are assets prioritized based on criticality?"
    - "Are assets prioritized based on resources?"
    - "Are assets prioritized based on impact on the mission?"
  ID.AM-08:
    - "Are systems managed throughout their life cycles, for example from acquisition to retirement?"
    - "Is hardware managed throughout its life cycle, for example from acquisition to retirement?"
    - "Is software managed throughout its life cycle, for example from acquisition to retirement?"
    - "Are services managed throughout their life cycles, for example from acquisition to retirement?"
    - "Is data managed throughout its life cycle, for example from acquisition to retirement?"
  ID.RA-01:
    - "Are vulnerabilities in assets identified?"
    - "Are vulnerabilities in assets validated?"
    - "Are vulnerabilities in assets recorded?"
  ID.RA-02:
    - "Is cyber threat intelligence received from information sharing forums and sources?"
  ID.RA-08:
    - "Are processes for receiving vulnerability disclosures established?"
    - "Are processes for analyzing vulnerability disclosures established?"
    - "Are processes for responding to vulnerability disclosures established?"
  PR.AA-01:
    - "Are identities and credentials for authorized users managed by the organization?"
    - "Are identities and credentials for services managed by the organization?"
    - "Are identities and credentials for hardware managed by the organization?"
  PR.AA-03:
    - "Are users authenticated?"
    - "Are services authenticated?"
    - "Is hardware authenticated?"
  PR.AA-05:
    - "Are access permissions, entitlements and authorizations defined in a policy?"
    - "Are access permissions, entitlements and authorizations managed?"
    - "Are access permissions, entitlements and authorizations enforced?"
    - "Are access permissions, entitlements and authorizations reviewed?"
    - "Do access permissions, entitlements and authorizations incorporate the principles of least privilege and separation of duties?"
  PR.AA-06:
    - "Is physical access to assets managed?"
    - "Is physical access to assets monitored?"
    - "Is physical access to assets enforced commensurate with risk?"
  PR.DS-01:
    - "Is the confidentiality of data at rest protected, for example by encryption?"
    - "Is the integrity of data at rest protected?"
    - "Is the availability of data at rest protected?"
  PR.DS-02:
    - "Is the confidentiality of data in transit protected, for example by encryption?"
    - "Is the integrity of data in transit protected?"
    - "Is the availability of data in transit protected?"
  PR.DS-11:
    - "Are backups of data created?"
    - "Are backups of data protected?"
    - "Are backups of data maintained?"
    - "Are backups of data tested?"
  PR.PS-01:
    - "Are configuration management practices, such as baseline configurations and change control, established?"
    - "Are configuration management practices, such as baseline configurations and change control, applied?"
  PR.PS-02:
    - "Is software maintained?"
    - "Is software replaced?"
    - "Is software removed commensurate with risk?"
  PR.PS-04:
    - "Are log records generated?"
    - "Are log records made available for continuous monitoring, for example centrally?"
  PR.PS-06:
    - "Are secure software development practices, such as security testing and code review, integrated?"
    - "Is the performance of secure software development practices monitored throughout the software development life cycle?"
  PR.IR-03:
    - "Are mechanisms implemented to achieve resilience requirements, such as recovery objectives, in normal and adverse situations?"
  PR.IR-04:
    - "Is adequate resource capacity to ensure availability maintained?"
  DE.CM-09:
    - "Are computing hardware and software monitored to find potentially adverse events?"
    - "Are runtime environments monitored to find potentially adverse events?"
    - "Is the data of computing hardware, software and runtime environments monitored to find potentially adverse events?"
  DE.AE-06:
    - "Is information on adverse events provided to authorized staff and tools, for example through alerts?"
  DE.AE-07:
    - "Are cyber threat intelligence and other contextual information integrated into the analysis of adverse events?"
  RS.MA-01:
    - "Is the incident response plan executed in coordination with relevant third parties once an incident is declared?"
  RS.AN-03:
    - "Is analysis performed to establish what has taken place during an incident and the root cause of the incident?"
  RS.CO-02:
    - "Are internal and external stakeholders, such as customers, notified of incidents?"
  RS.MI-01:
    - "Are incidents contained?"
  RC.RP-01:
    - "Is the recovery portion of the incident response plan, such as disaster recovery failover and restore, executed once initiated from the incident response process?"
paraphrase_words:
  ID.AM-08: {acquisition: cycles, retirement: cycles}
  PR.DS-01: {encryption: protected}
  PR.DS-02: {encryption: protected}
  PR.PS-01: {baseline: configuration, change: management, control: management}
  PR.PS-04: {centrally: available}
  PR.PS-06: {testing: practices, code: software, review: practices}
  PR.IR-03: {recovery: resilience, objectives: requirements}
  DE.AE-06: {alerts: information}
  RS.CO-02: {customers: stakeholders}
  RC.RP-01: {disaster: recovery, failover: recovery, restore: recovery}
```

Do not run `datakit.csf build` yet: Step 5 writes the code that builds the parts.

- [ ] **Step 3: Write the failing datakit tests**

Append to `tests/datakit/test_csf.py` (and add `from collections.abc import Callable` to its imports):

```python
def test_inflections_of_nists_words_are_nist_words() -> None:
    nist = "Inventories of hardware managed by the organization are maintained; processes are established"
    assert csf.added_words("Is an inventory of hardware maintained, and are processes managed?", nist) == []
    assert csf.added_words("Is hardware encrypted by the vendor?", nist) == ["encrypted", "vendor"]


def test_every_checked_outcome_has_parts_and_no_other_outcome_does() -> None:
    _, tiers, built = _committed()
    parts = {o["id"]: o["parts"] for o in built["outcomes"]}
    assert all(parts[i] for i in tiers["checked"]) and sum(map(len, parts.values())) == 73
    assert all(parts[o["id"]] == [] for o in built["outcomes"] if o["tier"] != "checked")
    assert all(len(m) <= csf.MAX_PARAPHRASE for m in tiers["paraphrase_words"].values())


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (lambda t: t["parts"].update({"PR.DS-11": []}), "checked PR.DS-11: no parts"),
        (lambda t: t["parts"].update({"GV.OC-01": ["Is it done?"]}), "parts GV.OC-01: not a checked outcome"),
        (
            lambda t: t["parts"].update({"RS.MI-01": ["Are incidents contained by the security team?"]}),
            "RS.MI-01 part 1: adds 'security', not in NIST's text",
        ),
        (  # a document name is an added word
            lambda t: t["parts"]["GV.PO-01"].append("Is the policy enforced, as the HR handbook says?"),
            "GV.PO-01 part 4: adds 'hr', not in NIST's text",
        ),
        (
            lambda t: t["parts"].update({"RS.MI-01": ['Are incidents "contained"?']}),
            "RS.MI-01 part 1: must be ASCII, quote nothing and end with '?'",
        ),
        (  # Ruling 11b: separation of duties may not be dropped
            lambda t: t["parts"].update(
                {"PR.AA-05": [q.replace(" and separation of duties", "") for q in t["parts"]["PR.AA-05"]]}
            ),
            "PR.AA-05: NIST's 'separation' is in no part",
        ),
        (
            lambda t: t["paraphrase_words"].pop("ID.AM-08"),
            "ID.AM-08 part 1: adds 'acquisition', not in NIST's text",
        ),
        (
            lambda t: t["paraphrase_words"].update({"RS.MI-01": {"isolation": "contained"}}),
            "RS.MI-01: paraphrase word 'isolation' is in no part",
        ),
        (  # I3: a paraphrase word names an instance of a NIST word of its own outcome
            lambda t: t["paraphrase_words"]["RC.RP-01"].update({"failover": "bcp"}),
            "RC.RP-01: paraphrase word 'failover' must map to a word of NIST's text, not 'bcp'",
        ),
        (
            lambda t: t["paraphrase_words"]["PR.PS-06"].update({"sast": "practices"}),
            "PR.PS-06: 4 paraphrase words, at most 3",
        ),
        (  # an added word enters only through an example clause
            lambda t: t["parts"]["PR.PS-04"].__setitem__(
                1, "Are log records made available centrally for continuous monitoring?"
            ),
            "PR.PS-04 part 2: 'centrally' stands outside an example clause",
        ),
        (  # R3: the clause ends at the next comma
            lambda t: t["parts"]["PR.PS-01"].__setitem__(
                0,
                "Are configuration management practices, such as baseline configurations,"
                " established with change control?",
            ),
            "PR.PS-01 part 1: 'change' stands outside an example clause",
        ),
        (  # R4: the revision-1 list form is named, not a crash
            lambda t: t["paraphrase_words"].update({"PR.DS-01": ["encryption"]}),
            "paraphrase_words PR.DS-01: must map each word to a NIST word",
        ),
    ],
)
def test_a_bad_part_is_named(edit: Callable[[dict[str, Any]], object], problem: str) -> None:
    nist, tiers, _ = _committed()
    edit(tiers)
    assert problem in csf.problems(nist, tiers, csf.build(nist, tiers))
```

- [ ] **Step 4: Run them to verify they fail**

Run: `pytest tests/datakit/test_csf.py -q`
Expected: FAIL. The new tests fail with `AttributeError: module 'datakit.csf' has no attribute 'added_words'` and
`KeyError: 'parts'`. `test_the_committed_data_matches_nists_extract` fails too, because the built file is stale
against ID.AM-08's new question.

- [ ] **Step 5: Write the part checks in `datakit/csf.py` and rebuild**

After `NIST_FIELDS`:

```python
# Question words a part may use besides NIST's own (CSF spec 4, amended): none names a thing or a requirement.
FRAME = frozenset(
    "a an the is are do does its their of and or to for in on at by with from once as such example through".split()
)
MAX_PARAPHRASE = 3  # words per outcome (adversary checkpoint 2, I3)
_WORD = re.compile(r"[a-z]+")
_EXAMPLE = re.compile(r"\b(?:such as|for example)\b")


def _stem(word: str) -> str:
    """Enough to match NIST's inflections: inventories/inventory, managed/manage, processes/process."""
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + ("y" if suffix == "ies" else "")
            break
    return word.removesuffix("e")


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("'s", ""))


def added_words(part: str, nist: str) -> list[str]:
    """The words of a part that are neither question words nor NIST's (compared by stem), in order."""
    have = {_stem(w) for w in words(nist)}
    return [w for w in words(part) if w not in FRAME and _stem(w) not in have]


def _part_problems(i: str, listed: list[Any], mapping: dict[str, Any], outcome: str, nist: str) -> list[str]:
    """Each part is a question in NIST's words for this outcome. Any other word stands in an example clause
    ("such as" or "for example", up to the next comma or the question mark) and is on the outcome's
    paraphrase_words, mapped to the NIST word it is an instance of (at most MAX_PARAPHRASE). Together the parts
    carry every word of NIST's outcome."""
    if not listed:
        return [f"checked {i}: no parts"]
    have = {_stem(w) for w in words(nist)}
    p = [
        f"{i}: paraphrase word {w!r} must map to a word of NIST's text, not {t!r}"
        for w, t in mapping.items()
        if not (isinstance(t, str) and _stem(t.lower()) in have)
    ]
    if len(mapping) > MAX_PARAPHRASE:
        p.append(f"{i}: {len(mapping)} paraphrase words, at most {MAX_PARAPHRASE}")
    for n, q in enumerate(listed, 1):
        if not (isinstance(q, str) and q.isascii() and q.rstrip().endswith("?") and '"' not in q):
            p.append(f"{i} part {n}: must be ASCII, quote nothing and end with '?'")
            continue
        # The example clause runs from "such as" / "for example" to the next comma or the question mark.
        m = _EXAMPLE.search(q.lower())
        in_example = set(words(re.split(r"[,?]", q.lower()[m.end() :])[0])) if m else set()
        for w in added_words(q, nist):
            if w not in mapping:
                p.append(f"{i} part {n}: adds {w!r}, not in NIST's text")
            elif w not in in_example:
                p.append(f"{i} part {n}: {w!r} stands outside an example clause")
    used = [w for q in listed if isinstance(q, str) for w in words(q)]
    stems = {_stem(w) for w in used}
    p += [
        f"{i}: NIST's {w!r} is in no part"
        for w in dict.fromkeys(words(outcome))
        if w not in FRAME and _stem(w) not in stems
    ]
    p += [f"{i}: paraphrase word {w!r} is in no part" for w in sorted(set(mapping) - set(used))]
    return p
```

`build` writes the parts:

```python
def build(nist: dict[str, Any], tiers: dict[str, Any]) -> dict[str, Any]:
    parts = tiers.get("parts") or {}

    def entry(o: dict[str, Any]) -> dict[str, Any]:
        tier = _tier(tiers, o["id"])
        question = (tiers.get(tier) or {}).get(o["id"]) if tier != "not_checked" else None
        listed = list(parts.get(o["id"]) or []) if tier == "checked" else []
        return {**o, "source_url": TOOL_URL, "tier": tier, "question": question, "parts": listed}
```

(the rest of `build` is unchanged). In `problems`, after the line `p += [f"{i}: in both checked and ask" ...]`:

```python
    parts, extra = tiers.get("parts") or {}, tiers.get("paraphrase_words") or {}
    text = {o["id"]: (o["outcome"], f"{o['outcome']} {o['category']}") for o in nist["outcomes"]}
    p += [f"parts {i}: not a checked outcome" for i in parts if i not in checked]
    p += [f"paraphrase_words {i}: not a checked outcome" for i in extra if i not in checked]
    for i in (i for i in checked if i in text):
        mapping = extra.get(i) or {}
        if not isinstance(mapping, dict):
            p.append(f"paraphrase_words {i}: must map each word to a NIST word")
            mapping = {}
        p += _part_problems(i, parts.get(i) or [], mapping, *text[i])
```

Run: `python -m datakit.csf build && pytest tests/datakit/test_csf.py -q`
Expected: `wrote data/csf/csf-2.0.json: 0 problems`, then PASS.

- [ ] **Step 6: Write the failing app tests**

`tests/test_csf_parts.py`:

```python
import itertools
import json
import uuid
from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import (
    BudgetExhausted,
    Citation,
    Conflict,
    ConflictSide,
    Decision,
    DocInfo,
    Draft,
    Dropped,
    ItemInput,
    ItemResult,
    Passage,
    Retrieval,
)
from app.db.models import LlmUsage
from app.llm.client import LLMRequest, LLMResult
from app.services import llm_budget
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import FakeLLM

LABELS = ("covered", "partly_covered", "not_met", "documents_disagree", "gap")
MODELS = {"stance": "m/stance", "draft": "m/draft"}
DOC = DocInfo("d1", "access-control-policy.md", "policy", "final", None, None, True)
QUOTE = "Every security incident is reviewed to find its root cause."


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _outcome(n: int) -> csf.Outcome:
    return replace(csf.framework().get("PR.AA-05"), parts=tuple(f"Is part {i} done?" for i in range(1, n + 1)))


def _part(n: int, label: str, line: int | None = None, doc: DocInfo = DOC) -> ItemResult:
    """A part's result as decide gives it: every label but Gap cites a line; a disagreement cites one line per side."""
    line = line or n
    p = Passage(f"c{line}", doc, line, (f"Access rule number {line} is enforced.",), None, (), None, False)
    decided, value = csf._DECIDE[label]  # type: ignore[index]
    stance = {"not_met": "no", "partly_covered": "partial"}.get(label, "yes")
    cite = Citation(p.chunk_id, doc.id, doc.filename, line, line, p.lines[0], stance)  # type: ignore[arg-type]
    cites: tuple[Citation, ...] = () if label == "gap" else (cite,)
    conflict = None
    if label == "documents_disagree":
        no = Citation(f"{p.chunk_id}n", "d9", "access-review-records.xlsx", 3, 3, "Status: Overdue", "no")
        cites = (cite, no)
        conflict = Conflict("documents-disagree", (ConflictSide("yes", (cite,), None), ConflictSide("no", (no,), None)))
    decision = Decision(decided, value, cites, (), conflict, None, 0.9)
    item = ItemInput(f"PR.AA-05#{n}", "q", None)
    return ItemResult(item, Retrieval((p,), ()), (), decision, Draft("", "template"), 0.001, 100)


def test_every_checked_outcome_has_its_parts_and_only_checked_ones_do() -> None:
    outcomes = csf.framework().outcomes
    assert all(o.parts for o in outcomes if o.tier == "checked")
    assert all(o.parts == () for o in outcomes if o.tier != "checked")
    assert sum(len(o.parts) for o in outcomes) == 73
    o = csf.framework().get("PR.DS-11")
    assert csf.part_inputs(o)[3] == ItemInput("PR.DS-11#4", "Are backups of data tested?", "Data Security")


def test_the_decide_mapping_is_the_inverse_of_the_gap_table() -> None:
    assert {gap: pair for pair, gap in csf._CHECKED.items()} == csf._DECIDE


@pytest.mark.parametrize(
    ("labels", "want"),
    [
        (("covered",), "covered"),
        (("covered", "covered", "covered"), "covered"),
        (("gap", "gap"), "gap"),
        (("covered", "gap"), "partly_covered"),
        (("partly_covered",), "partly_covered"),
        (("covered", "partly_covered"), "partly_covered"),
        (("covered", "not_met"), "not_met"),  # a stated No outranks evidenced parts
        (("partly_covered", "not_met", "gap"), "not_met"),
        (("not_met", "documents_disagree"), "documents_disagree"),  # a disagreement outranks a stated No
        (("covered", "documents_disagree", "gap"), "documents_disagree"),
    ],
)
def test_parts_combine_in_the_spec_order(labels: tuple[str, ...], want: str) -> None:
    assert csf.combine(labels) == want  # type: ignore[arg-type]


@pytest.mark.parametrize("n", [1, 2, 3])
def test_every_mix_of_part_labels_follows_the_precedence(n: int) -> None:
    for labels in itertools.product(LABELS, repeat=n):
        got = csf.combine(labels)  # type: ignore[arg-type]
        assert (got == "documents_disagree") == ("documents_disagree" in labels), labels
        assert (got == "not_met") == ("not_met" in labels and "documents_disagree" not in labels), labels
        assert (got == "covered") == (set(labels) == {"covered"}), labels
        assert (got == "gap") == (set(labels) == {"gap"}), labels
        assert n > 1 or got == labels[0]  # one part maps to itself: spec 5.3's table


def test_an_outcome_without_parts_has_no_label() -> None:
    with pytest.raises(ValueError, match="at least one part"):
        csf.combine([])


@pytest.mark.parametrize("n", [1, 2, 3])
def test_no_outcome_is_covered_or_partly_without_a_citation(n: int) -> None:
    o = _outcome(n)
    for labels in itertools.product(LABELS, repeat=n):
        r = csf.aggregate(o, [_part(i, x) for i, x in enumerate(labels, 1)])
        shown = csf.gap_label(o, r.decision.label, r.decision.value)
        assert shown == csf.combine(labels), labels  # type: ignore[arg-type]
        assert bool(r.decision.citations) == (shown != "gap"), labels  # ck_answers_cited


def test_citations_and_passages_are_the_parts_union_without_duplicates() -> None:
    o = _outcome(3)
    r = csf.aggregate(o, [_part(1, "covered", 4), _part(2, "covered", 4), _part(3, "partly_covered", 7)])
    assert [(c.line_start, c.stance) for c in r.decision.citations] == [(4, "yes"), (7, "partial")]
    assert [p.chunk_id for p in r.retrieval.passages] == ["c4", "c7"]
    assert (r.item, r.stances, r.cost_usd, r.latency_ms) == (csf.item_input(o), (), 0.003, 300)
    same_line = csf.aggregate(_outcome(2), [_part(1, "covered", 4), _part(2, "partly_covered", 4)])
    assert [c.stance for c in same_line.decision.citations] == ["yes", "partial"]  # M2: stance is in the key


def test_a_quote_failure_in_any_part_lowers_the_confidence_as_decide_does() -> None:
    dropped = (Dropped("c9", "d1", DOC.filename, "containment", "a quote not in the line"),)
    failed = _part(2, "covered")
    failed = replace(failed, decision=replace(failed.decision, dropped=dropped))
    r = csf.aggregate(_outcome(2), [_part(1, "covered"), failed])
    assert (r.decision.confidence, r.decision.dropped) == (0.7, dropped)
    assert csf.aggregate(_outcome(2), [_part(1, "covered"), _part(2, "covered")]).decision.confidence == 0.9


def test_a_stated_no_is_quoted_from_its_own_part_never_over_yes_lines() -> None:
    """Adversary C2: parts covered in documents A and B and stated No in C; the outcome is Not met, and its
    explanation quotes C's line only, after the group line."""
    a, b, c = (replace(DOC, id=x, filename=f"{x}-policy.md") for x in ("a", "b", "c"))
    parts = [_part(1, "covered", doc=a), _part(2, "covered", doc=b), _part(3, "not_met", doc=c)]
    r = csf.aggregate(_outcome(3), parts)
    assert (r.decision.label, r.decision.value) == ("verified", "No")
    assert r.draft.text == (
        "Evidenced: parts 1, 2. Stated as not done: part 3. "
        'Is part 3 done? No. The c policy says: "Access rule number 3 is enforced."'
    )
    assert [x.stance for x in r.decision.citations] == ["yes", "yes", "no"]  # a display record: stances kept


def test_the_explanation_shows_only_the_deciding_parts() -> None:
    o = _outcome(3)
    r = csf.aggregate(o, [_part(1, "covered"), _part(2, "documents_disagree"), _part(3, "gap")])
    assert r.decision.conflict is not None and r.draft.source == "template"
    assert r.draft.text.startswith(
        "Evidenced: part 1. Documents disagree: part 2. No evidence: part 3. Is part 2 done? The documents disagree."
    )
    assert "Is part 1 done?" not in r.draft.text
    partly = csf.aggregate(o, [_part(1, "covered"), _part(2, "partly_covered"), _part(3, "gap")])
    assert "Is part 1 done? Yes." in partly.draft.text and "Is part 2 done? Partly." in partly.draft.text
    gap = csf.aggregate(o, [_part(i, "gap") for i in (1, 2, 3)])
    assert gap.draft.text == "No evidence: parts 1, 2, 3."


def _stance(kind: str) -> str:
    quote = "" if kind == "irrelevant" else QUOTE
    return json.dumps({"passages": [{"passage": 1, "stance": kind, "quote": quote, "note": "judged"}]})


def _two_parts() -> csf.Outcome:
    return replace(
        csf.framework().get("RS.AN-03"),
        parts=("Is what took place during an incident established?", "Is the root cause of an incident established?"),
    )


def _incident_policy(s: Session) -> uuid.UUID:
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="incident-policy.docx"), line_start=3, line_end=3, text=QUOTE)
    s.commit()
    return ws.id


def test_each_part_is_spent_and_judged_with_no_draft_and_no_open_transaction(s: Session, db: Engine) -> None:
    ws = _incident_policy(s)

    class Watching(FakeLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.step} ran inside an open transaction"
            return super().complete(req)

    o = _two_parts()
    llm = Watching([_stance("irrelevant"), _stance("yes")])
    parts = csf.check_parts(s, ws, o, llm, MODELS, spender(s, ws))
    assert [(q.step, q.item_id) for q in llm.requests] == [("stance", "RS.AN-03#1"), ("stance", "RS.AN-03#2")]
    assert all(part in q.user for part, q in zip(o.parts, llm.requests, strict=True))
    assert [csf.part_label(p) for p in parts] == ["gap", "covered"]
    with Session(db) as other:  # each call was spent and committed first; no draft was spent
        used = other.execute(select(LlmUsage.kind, LlmUsage.calls).where(LlmUsage.workspace_id == ws)).all()
    assert [tuple(u) for u in used] == [("stance", 2)]
    r = csf.aggregate(o, parts)
    assert csf.gap_label(o, r.decision.label, r.decision.value) == "partly_covered"
    assert [c.line_start for c in r.decision.citations] == [3]
    assert r.draft.text.startswith(f"Evidenced: part 2. No evidence: part 1. {o.parts[1]} Yes.")


def test_a_refused_stance_budget_stops_the_outcome_after_the_parts_it_paid_for(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    ws = _incident_policy(s)
    llm = FakeLLM([_stance("yes")])
    with pytest.raises(BudgetExhausted):
        csf.check_outcome(s, ws, _two_parts(), llm, MODELS, spender(s, ws))
    assert [q.step for q in llm.requests] == ["stance"]
```

In `tests/test_csf_framework.py`:
- Add two cases to the parametrize list of `test_the_loader_rejects_a_bad_data_file`:

  ```python
          (
              lambda os: next(o for o in os if o["tier"] == "checked").update(parts=["  "]),
              "a checked outcome needs parts",
          ),
          (lambda os: os[0].update(parts=["Is it done?"]), "GV.OC-01: only a checked outcome has parts"),
  ```

- In `test_a_changed_tier_list_gives_a_new_questionnaire`, add a second change that touches one part only (minor
  M6). After the reworded question's assertions:

  ```python
      first = q.id
      recut = replace(
          reworded,
          outcomes=tuple(
              replace(o, parts=("Is the policy approved?",)) if o.id == "GV.PO-01" else o for o in reworded.outcomes
          ),
      )
      monkeypatch.setattr(csf, "framework", lambda: recut)
      assert csf.questionnaire_for(s, ws.id, "govern").id != first  # a changed part alone gives a new questionnaire
  ```

- Replace `test_a_checked_outcome_runs_the_ordinary_pipeline` with the version below. Add `Draft` to the
  `app.contracts` import and `from app.draft import check`. PR.DS-01 now has three parts, so the expected calls go
  from `["stance", "draft"]` to three stance calls. The explanation is code (spec 5.3, amended), and this test now
  pins it in full. It is stricter, not weaker.

  ```python
  def test_a_checked_outcome_runs_the_ordinary_pipeline(s: Session) -> None:
      ws = f.workspace(s)
      doc = f.document(s, ws, filename="crypto-policy.docx")
      f.chunk(s, doc, line_start=4, line_end=4, text=QUOTE)
      s.commit()
      yes = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
      nothing = json.dumps({"passages": [{"passage": 1, "stance": "irrelevant", "quote": "", "note": "other"}]})
      llm = FakeLLM([yes, nothing, nothing])  # confidentiality, integrity, availability
      o = csf.framework().get("PR.DS-01")
      r = csf.check_outcome(s, ws.id, o, llm, MODELS, spender(s, ws.id))
      assert r is not None and r.item == csf.item_input(o)
      assert csf.gap_label(o, r.decision.label, r.decision.value) == "partly_covered"
      assert [req.step for req in llm.requests] == ["stance"] * 3
      text = f'Evidenced: part 1. No evidence: parts 2, 3. {o.parts[0]} Yes. The crypto policy says: "{QUOTE}"'
      assert r.draft == Draft(text, "template")
      # M4: every quote in the explanation is a cited line (the part numbers are code's, not evidence)
      assert [p for p in check(r.draft.text, r.decision, ["crypto-policy.docx"]) if p.startswith("quote")] == []
  ```

- [ ] **Step 7: Run them to verify they fail**

Run: `pytest tests/test_csf_parts.py tests/test_csf_framework.py -q`
Expected: FAIL. You should see `AttributeError: module 'app.csf' has no attribute '_DECIDE'` (and `combine`,
`aggregate`, `part_inputs`, `check_parts`), `TypeError: ... unexpected keyword argument 'parts'` from `replace`, and
the PR.DS-01 test's extra `draft` step.

- [ ] **Step 8: Write the parts into `app/csf.py`**

Change the imports to:

```python
from collections.abc import Callable, Iterable, Mapping, Sequence
...
from app.contracts import (
    Decision,
    Draft,
    Dropped,
    ItemInput,
    ItemLabel,
    ItemResult,
    Label,
    OpenItem,
    QueueEntry,
    Retrieval,
    Spend,
    Value,
)
from app.db.models import Item, Questionnaire, Workspace
from app.decide import CONFIDENCE, QUOTE_FAILURES
from app.draft import template_answer
```

Next to `GapLabel`: `PartLabel = Literal["covered", "partly_covered", "not_met", "documents_disagree", "gap"]  # a
Checked part's label (M12)`. Retype `_CHECKED` as `dict[tuple[str, str | None], PartLabel]`, then add:

```python
_DECIDE: dict[PartLabel, tuple[Label, Value | None]] = {  # the inverse of _CHECKED: a combined label as decide's
    "covered": ("verified", "Yes"),
    "partly_covered": ("partial", "Partial"),
    "not_met": ("verified", "No"),
    "documents_disagree": ("conflict", None),
    "gap": ("unknown", None),
}
PART_WORDS: dict[PartLabel, str] = {  # the explanation's groups, in this order
    "covered": "Evidenced",
    "partly_covered": "Partly evidenced",
    "not_met": "Stated as not done",
    "documents_disagree": "Documents disagree",
    "gap": "No evidence",
}
_DECIDING: dict[PartLabel, tuple[PartLabel, ...]] = {  # whose quotes explain each combined label (spec 5.3, C2)
    "documents_disagree": ("documents_disagree",),
    "not_met": ("not_met",),
    "covered": ("covered",),
    "partly_covered": ("covered", "partly_covered"),
    "gap": (),
}
```

`Outcome` gains a last field: `parts: tuple[str, ...] = ()  # VART's: NIST's text cut by spec 4's rule; checked
only`. `framework()` passes `tuple(o["parts"])` after `o["question"]`. In `_validate`, after the question check:

```python
        if o.tier == "checked" and not (o.parts and all(p.strip() for p in o.parts)):
            raise ValueError(f"{o.id}: a checked outcome needs parts")
        if o.tier != "checked" and o.parts:
            raise ValueError(f"{o.id}: only a checked outcome has parts")
```

In `_digest`: `rows = [[o.id, o.tier, o.question, o.category, list(o.parts)] for o in outcomes]`.

Replace `evidence` and `check_outcome`, and add the rest after `evidence`:

```python
def part_inputs(o: Outcome) -> tuple[ItemInput, ...]:
    """Each part as its own item (CSF spec 5.2, amended); the key names the outcome and the part's place."""
    return tuple(ItemInput(f"{o.id}#{n}", p, o.category) for n, p in enumerate(o.parts, 1))


def evidence(session: Session, workspace_id: uuid.UUID, item: ItemInput) -> Retrieval:
    """What one part of a Checked outcome is judged on (Ruling 9, spec 5.3 "checked against documents"): its
    retrieval without the visitor's stored answers, each dropped with reason 'statement' before any model sees
    it. An answer reaches a Checked outcome only as a suggestion the visitor accepts (Plan 6B)."""
    r = retrieve(session, workspace_id, item.question, item.topic)
    said = [p for p in r.passages if p.doc.kind == "statement"]
    return Retrieval(
        tuple(p for p in r.passages if p.doc.kind != "statement"),
        r.dropped + tuple(Dropped(p.chunk_id, p.doc.id, p.doc.filename, "statement") for p in said),
    )


def part_label(r: ItemResult) -> PartLabel:
    """A part's label: its decide output through spec 5.3's table."""
    return _CHECKED[(r.decision.label, r.decision.value)]


def combine(labels: Sequence[PartLabel]) -> PartLabel:
    """An outcome's label from its parts' labels (CSF spec 5.3, amended); the first rule that applies wins:
    any part disagreeing is Documents disagree; any part stated No is Not met; every part Covered is Covered;
    every part Gap is Gap; any other mix is Partly covered. One part maps to itself."""
    if not labels:
        raise ValueError("an outcome needs at least one part")
    if "documents_disagree" in labels:
        return "documents_disagree"
    if "not_met" in labels:
        return "not_met"
    if all(x == "covered" for x in labels):
        return "covered"
    if all(x == "gap" for x in labels):
        return "gap"
    return "partly_covered"


def _unique[T](items: Iterable[T], key: Callable[[T], object]) -> tuple[T, ...]:
    """The first of each key, in order."""
    seen: dict[object, T] = {}
    for x in items:
        seen.setdefault(key(x), x)
    return tuple(seen.values())


def _numbers(ns: list[int]) -> str:
    return f"part {ns[0]}" if len(ns) == 1 else "parts " + ", ".join(map(str, ns))


def explain(o: Outcome, parts: Sequence[ItemResult]) -> str:
    """The outcome's explanation (CSF spec 5.3, amended), by code with no model call: the part numbers by
    label, then each part that decided the combined label as its question and its own template answer, so a
    quote always stands beside the stance it was judged with and a stated No is never shown over yes lines."""
    labels = [part_label(r) for r in parts]
    deciding = _DECIDING[combine(labels)]
    groups = [
        f"{word}: {_numbers([n for n, x in enumerate(labels, 1) if x == label])}."
        for label, word in PART_WORDS.items()
        if label in labels
    ]
    answers = [
        f"{q} {template_answer(r.decision)}"
        for q, r, x in zip(o.parts, parts, labels, strict=True)
        if x in deciding
    ]
    return " ".join([*groups, *answers])


def aggregate(o: Outcome, parts: Sequence[ItemResult]) -> ItemResult:
    """One result for the outcome from its parts' results, in part order (CSF spec 5.3, amended). The Decision
    is a display record: the label by `combine`; every part's citations (each keeping its own part's stance),
    drops and passages without duplicates; the first disagreeing part's conflict; the parts' scope notes;
    decide's confidence rule (spec 6.7 rule 9) over the merged drops. The explanation is `explain`. Per-passage
    stances stay with the parts (`check_parts`): their indices point into each part's own passages."""
    label, value = _DECIDE[combine([part_label(r) for r in parts])]
    dropped = _unique((d for r in parts for d in r.decision.dropped), lambda d: (d.chunk_id, d.reason, d.quote))
    confidence = CONFIDENCE[label] - (0.2 if any(d.reason in QUOTE_FAILURES for d in dropped) else 0.0)
    decision = Decision(
        label,
        value,
        _unique(
            (c for r in parts for c in r.decision.citations),
            lambda c: (c.document_id, c.line_start, c.line_end, c.quote, c.stance),
        ),
        dropped,
        next((r.decision.conflict for r in parts if r.decision.conflict is not None), None),
        " ".join(_unique((n for r in parts if (n := r.decision.scope_note)), lambda n: n)) or None,
        round(max(confidence, 0.0), 2),
    )
    retrieval = Retrieval(
        _unique((p for r in parts for p in r.retrieval.passages), lambda p: p.chunk_id),
        _unique((d for r in parts for d in r.retrieval.dropped), lambda d: (d.chunk_id, d.reason, d.quote)),
    )
    return ItemResult(
        item_input(o),
        retrieval,
        (),
        decision,
        Draft(explain(o, parts), "template"),
        round(sum(r.cost_usd for r in parts), 6),
        sum(r.latency_ms for r in parts),
    )


def _without_draft(spend: Spend) -> Spend:
    """A part's own draft is never shown. Refusing its budget makes write_draft return the template with no
    model call and nothing spent; the outcome's explanation is `explain`. Pinned by
    tests/test_csf_parts.py::test_each_part_is_spent_and_judged_with_no_draft_and_no_open_transaction: if
    write_draft ever raises on a refused budget, that test fails before any CSF run does (M7)."""
    return lambda step: step != "draft" and spend(step)


def check_parts(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> list[ItemResult]:
    """The parts' own results, in part order (CSF spec 5.2, amended): each part through the ordinary pipeline
    (answer_retrieved spends before each model call and commits before it, so no transaction is open across
    one) on documents only (`evidence`). Ask me: [] with no retrieval and no model call (it has no parts). Not
    checked: never part of a run."""
    if o.tier == "not_checked":
        raise ValueError(f"{o.id} is {NOT_CHECKED}")
    no_draft = _without_draft(spend)
    return [
        answer_retrieved(session, workspace_id, item, evidence(session, workspace_id, item), llm, models, no_draft)
        for item in part_inputs(o)
    ]


def check_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult | None:
    """One outcome of a gap-check run (CSF spec 5.2-5.5, amended): Checked, its parts combined (`aggregate`);
    Ask me, None, with no retrieval and no model call (the visitor answers it through ask_queue and
    store_statement); not checked, ValueError."""
    parts = check_parts(session, workspace_id, o, llm, models, spend)
    return aggregate(o, parts) if parts else None
```

Change the first sentence of the module docstring to: "... the gap labels, a display mapping over decide's output
per part, combined by code (decide itself does not change)."

Run: `pytest tests/test_csf_parts.py tests/test_csf_framework.py -q --cov=app.csf --cov-branch --cov-report=term-missing --cov-fail-under=100 && mypy app`
Expected: PASS, `app/csf.py` at 100% with no missing lines or partial branches, and `Success: no issues found`. If a
line written before Task 8 shows as missing, report it; do not add a test for it in this task.

- [ ] **Step 9: The eval harness runs parts and reports them (adversary I4, I7)**

In `evals/gap.py`:
- Import `field` from `dataclasses`.
- `GapPack` gains a last field
  `missing_parts: dict[str, tuple[int, ...]] = field(default_factory=dict)  # Checked id -> parts the key says lack evidence`.
  `load()` passes `{m.csf_id: m.missing_parts for m in gap.outcomes if m.missing_parts}`.
- `GapObserved` gains a last field
  `parts: dict[str, list[ItemResult]] = field(default_factory=dict)  # Checked id -> its parts' own results`.
- The run loop:

  ```python
              results: dict[str, ItemResult] = {}
              parts: dict[str, list[ItemResult]] = {}
              for o in outcomes:
                  answered = csf.check_parts(session, ws.id, o, log, models, always)
                  if answered:  # Ask me: [] (no parts, no model call)
                      parts[o.id] = answered
                      results[o.id] = csf.aggregate(o, answered)
  ```

  `results` was filled by `check_outcome` before; the `if o.id not in results` test for Ask-me answers stays as it
  is.
- The probe runs once per part:

  ```python
              for o in outcomes:
                  for item in csf.part_inputs(o):
                      found = csf.evidence(session, ws.id, item)
                      kept = sum(p.doc.id in said for p in found.passages)
                      probe_kept += kept
                      probe_seen += kept + sum(d.document_id in said for d in found.dropped)
  ```

- Build `GapObserved(..., probe_kept, probe_seen, parts)`.
- In the report's `items` entry, after `"draft": r.draft.source,` add `"explanation": r.draft.text,` and
  `"parts": [_part_report(p) for p in obs.parts.get(code, [])],`, with:

  ```python
  def _part_report(r: ItemResult) -> dict[str, Any]:
      """One part as gap-dev.json shows it: file names and lines, never database ids, so a replay is identical."""
      return {
          "key": r.item.key,
          "label": csf.part_label(r),
          "citations": [f"{c.filename}:{c.line_start}:{c.stance}" for c in r.decision.citations],
          "dropped": sorted(f"{d.filename}:{d.reason}" for d in r.decision.dropped),
          "passages": [f"{p.doc.filename}:{p.line_start}" for p in r.retrieval.passages],
      }
  ```

- In `score_gap`, before the retrieval recall:

  ```python
      # Part agreement (I4; reported, never a gate): over the outcomes whose key names missing parts, the engine
      # left every missing part Gap or Partly and did not leave all the other parts Gap
      agree = named = 0
      for c, missing in pack.missing_parts.items():
          labels = [csf.part_label(r) for r in obs.parts.get(c, [])]
          if not labels:
              continue
          named += 1
          others = [x for n, x in enumerate(labels, 1) if n not in missing]
          agree += all(labels[n - 1] in ("gap", "partly_covered") for n in missing) and (
              not others or any(x != "gap" for x in others)
          )
      m["part_agreement"] = score._gated(agree, named)
  ```

- In the module docstring, replace "every Checked outcome through answer_item" with "every Checked outcome part by
  part through answer_retrieved (app.csf.check_parts), combined by app.csf.aggregate".

In `tests/test_eval_gap.py`:
- The three tests that stub the engine stub `check_parts` now. In each, the fake returns
  `[] if o.tier == "ask" else [_result(o.id, UNKNOWN)]` (with return type `list[ItemResult]`), and
  `monkeypatch.setattr(csf, "check_outcome", check)` becomes `monkeypatch.setattr(csf, "check_parts", check)`. The
  Ruling 1 test's fake keeps `events.append(("check", o.id))` for Checked outcomes only.
- The monkeypatched `evidence` takes an item:
  `monkeypatch.setattr(csf, "evidence", lambda s, ws, item: retrieve(s, ws, item.question, item.topic))`.
- In the first run test, after the `label_accuracy` assertion:

  ```python
      assert report["items"]["PR.DS-11"]["parts"] == [
          {"key": "PR.DS-11", "label": "gap", "citations": [], "dropped": [], "passages": []}
      ]
      assert "part_agreement" in m and "part_agreement" not in gap.GATES
  ```

- Add:

  ```python
  def test_part_agreement_is_reported_and_never_gated() -> None:
      pack = gap.load()
      obs = _perfect(pack)
      yes = Decision("verified", "Yes", (), (), None, None, 0.9)
      assert pack.missing_parts["PR.AA-01"] == (3,)  # users, services, hardware: the key lacks hardware
      obs.parts = {"PR.AA-01": [_result("PR.AA-01#1", yes), _result("PR.AA-01#2", yes), _result("PR.AA-01#3", UNKNOWN)]}
      assert gap.score_gap(pack, obs)["part_agreement"] == 1.0
      obs.parts["PR.AA-01"] = [_result("PR.AA-01#1", UNKNOWN), _result("PR.AA-01#2", yes), _result("PR.AA-01#3", yes)]
      assert gap.score_gap(pack, obs)["part_agreement"] == 0.0  # right label, wrong parts
      assert "part_agreement" not in gap.GATES
  ```

Run: `pytest tests/test_eval_gap.py -q` (it fails until Step 10 adds `missing_parts`; it is run again in Step 10).

- [ ] **Step 10: The key adopts judge 2 under C1 (Rulings 15, 17)**

The key stays outcome-level and code-derived, never computed through `app.csf.combine`. Judge 2's changes go into the
fact sheet, never into `csf-core.yaml`:
- PR.DS-11 keeps judge 2's own fallback: it stays Partly covered, and its interval disagreement goes into `missing`
  (C1).
- The per-part re-judge (Ruling 19) keeps PR.DS-01 Covered and registers its integrity line; that is a fact-sheet
  correction, so the key's evidence covers the part.
- The re-judge makes PR.DS-02 Partly covered with `missing_parts: [3]` (availability) and registers its integrity
  line.

The result is 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree and 3 Gap.

First the tests. In `tests/datakit/test_gap.py`, `test_the_key_plants_what_the_spec_asks`:

```python
    assert by_label["documents_disagree"] == {"PR.AA-05", "DE.AE-06"}
    assert by_label["not_met"] == {"ID.RA-02", "DE.AE-07"}
    assert by_label["gap"] == {"ID.AM-03", "PR.AA-06", "PR.IR-04"}
    assert by_label["partly_covered"] == {
        "PR.AA-03",
        "RS.MA-01",
        "RS.CO-02",
        "PR.DS-02",
        "PR.DS-11",
        "PR.IR-03",
        "ID.AM-05",
        "ID.AM-08",
        "GV.PO-02",
        "PR.AA-01",
        "PR.PS-02",
        "PR.PS-06",
    }
    assert {"RS.AN-03", "RS.MI-01"} <= by_label["covered"]
    assert Counter(labels.values())["covered"] == 12
```

In `test_a_label_override_changes_the_derived_label`:

```python
    assert changed == {
        "PR.DS-02", "PR.DS-11", "PR.IR-03", "ID.AM-05", "ID.AM-08", "GV.PO-02", "PR.AA-01", "PR.PS-02", "PR.PS-06"
    }
```

Add:

```python
def test_the_per_part_rejudge_is_in_the_key() -> None:
    """Ruling 19: PR.DS-01 stays Covered with its integrity line as key evidence; PR.DS-02 is Partly covered,
    availability in transit missing, with its integrity line as key evidence."""
    facts, g = gap.load("dev")
    keys = {k.code: k for k in gap.derive_gap(facts, g).items}
    evidence = {c: {(e.doc, e.quote) for e in keys[c].evidence} for c in ("PR.DS-01", "PR.DS-02")}
    assert ("lmp", "Improper alteration or loss of sensitive information.") in evidence["PR.DS-01"]
    scope = "This policy applies to all Kestrelyn systems that store, transmit, or process sensitive information."
    assert ("lmp", scope) in evidence["PR.DS-02"]
    assert (keys["PR.DS-01"].expected_label, keys["PR.DS-02"].expected_label) == ("verified", "partial")
```

and:

```python
@pytest.mark.parametrize(
    ("update", "problem"),
    [
        ({"missing_parts": ()}, "outcome PR.DS-11: a label override needs missing_parts"),
        ({"missing_parts": (9,)}, "outcome PR.DS-11: no part 9"),
        ({"label": None, "missing": None}, "outcome PR.DS-11: missing_parts without a label override"),
    ],
)
def test_an_override_names_the_parts_it_misses(
    monkeypatch: pytest.MonkeyPatch, update: dict[str, object], problem: str
) -> None:
    facts, g = gap.load("dev")
    outcomes = tuple(o.model_copy(update=update) if o.csf_id == "PR.DS-11" else o for o in g.outcomes)
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    assert problem in gap.check("dev")


def test_a_planted_conflict_must_be_visible_to_a_part_without_a_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adversary C1: 'performed annually' is a no only against a question that says quarterly; a CSF part
    states no interval, so trap X1 cannot be a CSF disagreement. The two real ones pass: DE.AE-06's no side is
    negated, PR.AA-05's is an overdue record row."""
    facts, g = gap.load("dev")
    remap = {"control": "backup-restore-test", "label": None, "missing": None, "missing_parts": ()}
    outcomes = tuple(o.model_copy(update=remap) if o.csf_id == "PR.DS-11" else o for o in g.outcomes)
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    found = gap.check("dev")
    assert "PR.DS-11: conflict X1 rests on a thresholded no the CSF part cannot see" in found
    assert not [p for p in found if p.startswith(("PR.AA-05:", "DE.AE-06:"))]
```

Run `pytest tests/datakit/test_gap.py -q`. Expected: FAIL (the key still holds 17 Covered; `missing_parts` is
unknown).

Then the code and the data.
- In `datakit/schemas.py`, `GapOutcome` gets after `missing`:

  ```python
      # The parts (1-based, data/csf/tiers.yaml) the override's `missing` names; required with `label` (adversary I4).
      missing_parts: tuple[int, ...] = ()
  ```

- In `datakit/gap.py`, import `is_usable_evidence` from `datakit.derive_key`. After the `a label override needs
  missing` check, add:

  ```python
      count = {o.id: len(o.parts) for o in checked()}
      p += [
          f"outcome {m.csf_id}: a label override needs missing_parts"
          for m in gap.outcomes
          if m.label and not m.missing_parts
      ]
      p += [
          f"outcome {m.csf_id}: missing_parts without a label override"
          for m in gap.outcomes
          if m.missing_parts and not m.label
      ]
      p += [
          f"outcome {m.csf_id}: no part {n}"
          for m in gap.outcomes
          for n in m.missing_parts
          if not 1 <= n <= count.get(m.csf_id, 0)
      ]
  ```

  After `control = {m.csf_id: m.control for m in gap.outcomes}`, add:

  ```python
      # A CSF part states no threshold (spec 4), so a planted disagreement must rest on a no the part can see: a
      # negated sentence or a record row's status, not a longer interval (spec 10, adversary C1).
      p += [
          f"{k.code}: conflict {k.conflict_trap} rests on a thresholded no the CSF part cannot see"
          for k in key.items
          if k.expected_label == "conflict"
          and not all(
              "negation" in s.flags or "Status: " in s.text
              for s in f.statements_for(control[k.code])
              if s.stance == "no" and is_usable_evidence(f, s)
          )
      ]
  ```

- In `data/dev/gap/facts.yaml`, end the header comment's `outcomes` paragraph with "... overrides the derived label
  for a broad outcome; `missing_parts:` gives the numbers of those parts in data/csf/tiers.yaml (blind judges 1 and
  2, Rulings 12, 15, 17 and 19)". Then change the nine override entries:

  ```yaml
    - {csf_id: GV.PO-02, control: policy-review, label: partly_covered, missing_parts: [2, 4], missing: "updated, and enforced to reflect changes in requirements, threats, technology and mission (judge 2: only reviewed, communicated and enforced have evidence)"}
    - {csf_id: ID.AM-05, control: data-classification, label: partly_covered, missing_parts: [2, 3, 4], missing: "criticality, resources and mission impact (only classification has evidence)"}
    - {csf_id: ID.AM-08, control: media-sanitization, label: partly_covered, missing_parts: [1, 3, 4], missing: "end-of-life for systems, software and services (only hardware disposal and data deletion have evidence)"}
    - {csf_id: PR.AA-01, control: sso, label: partly_covered, missing_parts: [3], missing: "identities and credentials for hardware (judge 2: only users and services have evidence)"}
    # PR.DS-02 (judge 2's per-part re-judge, Ruling 19): confidentiality (crypto) and integrity (lmp scope line) have
    # evidence; no line protects the availability of data in transit.
    - {csf_id: PR.DS-02, control: encryption-in-transit, label: partly_covered, missing_parts: [3], missing: "availability of data in transit (judge 2 re-judge: no redundancy, DoS or rate-limit line; pentest KL-26-01 reports missing rate limiting)"}
    # PR.DS-11 (judge 2's fallback, Ruling 17 / adversary C1): the restore-test interval disagreement (policy quarterly,
    # DR plan annually) is a no only against a stated threshold, which a CSF part may not state; it is reported here.
    - {csf_id: PR.DS-11, control: backups, label: partly_covered, missing_parts: [2, 3], missing: "protected and maintained (no line on backup protection, retention or integrity); tested: the continuity policy says quarterly and the DR plan annually, an interval disagreement the part cannot see (spec 10)"}
    - {csf_id: PR.PS-02, control: patch-sla, label: partly_covered, missing_parts: [2, 3], missing: "replaced (no end-of-life or unsupported-software line); removed commensurate with risk has weak evidence only (judge 2)"}
    - {csf_id: PR.PS-06, control: sast, label: partly_covered, missing_parts: [2], missing: "performance monitored (judge 2: no metric or review of how the practices perform)"}
    - {csf_id: PR.IR-03, control: rto-rpo, label: partly_covered, missing_parts: [1], missing: "normal situations, and requirements achieved (only the RTO and RPO targets have evidence, no test shows them met)"}
  ```

  These numbers follow Step 2's parts: GV.PO-02 is 2 updated and 4 enforced-to-reflect; ID.AM-05 is 2 criticality,
  3 resources and 4 impact on the mission; ID.AM-08 is 1 systems, 3 software and 4 services; PR.AA-01 is 3
  hardware; PR.DS-02 is 3 availability; PR.DS-11 is 2 protected and 3 maintained; PR.PS-02 is 2 replaced and 3
  removed; PR.PS-06 is 2 monitored; PR.IR-03 has one part.

  Register the re-judge's integrity lines (a fact-sheet correction, Rulings 11c, 12 and 19). Append to `statements`:

  ```yaml
    # PR.DS-01 / PR.DS-02 integrity parts (judge 2's per-part re-judge, Ruling 19): the logging policy guards against
    # improper alteration (line 9) of sensitive information on systems that store, transmit or process it (line 10).
    - id: lmp-integrity-at-rest
      doc: lmp
      control: encryption-at-rest
      stance: yes
      text: "Improper alteration or loss of sensitive information."
    - id: lmp-integrity-in-transit
      doc: lmp
      control: encryption-in-transit
      stance: yes
      text: "This policy applies to all Kestrelyn systems that store, transmit, or process sensitive information."
  ```

Run: `python -m datakit.gap dev && python -m datakit.validate all && pytest tests/datakit/test_gap.py tests/test_eval_gap.py -q`
Expected: the key is rewritten, validation finds 0 problems, and the tests PASS. `git diff data/dev/key/` changes:
- GV.PO-02, PR.AA-01, PR.PS-02, PR.PS-06 and PR.DS-02 go from verified Yes to partial;
- PR.DS-01 gains the lmp line 9 evidence, and PR.DS-02 the lmp line 10 evidence;
- PR.DS-11 is unchanged, since it was already partial.

- [ ] **Step 11: The updated counts and the whole chain**

The counts that move together, each pinned by a test:
- 73 parts (`tests/datakit/test_csf.py`, `tests/test_csf_parts.py`);
- expected 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree, 3 Gap (`tests/datakit/test_gap.py`);
- 9 overrides with `missing_parts` (`tests/datakit/test_gap.py`).

These stay the same: the tiers (31 / 5 / 70, 36 in the core), and `round(3 / 31, 4)` in `tests/test_eval_gap.py`.
`MIN_PLANTED`'s two disagreements are still met.

Run, on `vart_test_csf`:

```bash
ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check && python -m datakit.validate all
python -m evals.run --pack dev; git diff --exit-code evals/results/latest.json evals/results/latest.md
python -m evals.run --pack gap-dev; echo "exit $?"
```

Expected:
- The chain passes.
- The dev pack prints its unchanged gate line (15/15) with no diff.
- gap-dev stops with `recording missing (...); re-record with --mode record` and `exit 2`, because every stance key
  changed. That is the lead's Step 13: never record from the implementer's session.

- [ ] **Step 12: Commit**

```bash
git add data/csf/tiers.yaml data/csf/csf-2.0.json datakit/csf.py tests/datakit/test_csf.py datakit/schemas.py datakit/gap.py tests/datakit/test_gap.py data/dev/gap/facts.yaml data/dev/key/csf-core.yaml app/csf.py tests/test_csf_framework.py tests/test_csf_parts.py evals/gap.py tests/test_eval_gap.py
git commit -m "feat(csf): per-part questions combined by code; key adopts blind judge 2 (CSF spec 4, 5.2-5.3 amended)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then the Opus review (Review Focus above).

- [ ] **Step 13 (lead, eval key): re-record gap-dev**

After the review is clean:

```bash
cd ~/Desktop/portfolio/projects/VART-wt-csf && source .venv/bin/activate
export DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_record_csf
alembic upgrade head
rm evals/recorded/gap-dev.jsonl  # every stance key changed and no draft is called: no old row is reused
(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack gap-dev --mode record)
```

Expected: 73 stance requests, of which 72 are live calls: GV.PO-02 part 3 has the same text as GV.PO-01 part 2, so
it replays that recording (R6). There is no draft call. The run costs about $0.07 and takes about 13 minutes. The last line reads
`N/9 gates pass`. If a stance call fails, the run stops; running it again resumes from the recordings already made.
From this commit on, the parts are frozen (spec 4). Then follow Task 7 Steps 2-3:

```bash
git add evals/recorded/gap-dev.jsonl evals/results/gap-dev.json evals/results/gap-dev.md
git commit -m "evals: gap-dev re-recorded with per-part questions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python -m evals.run --pack gap-dev; echo "exit $?"; python -m evals.run --pack dev; git diff --exit-code evals/results && git status --short evals/
```

Expected: the same gate line and exit code as the record run, the dev pack 15/15, and no diff.

- [ ] **Step 14 (lead): baseline**

If `label_accuracy` is below 0.80, diagnose before changing anything. Read the per-part report in `gap-dev.json` and
sort each miss into part retrieval, part stance, part wording (a frozen part: a change is a tuning round with a
change-log line that cites NIST) or the key. Ruling 16 applies: at most 2 rounds under Task 7 Step 4's rules, then
Tarun.

Then Task 7 Step 5. The report to Tarun lists:
- the gate table and `part_agreement` (reported, not a gate). The metric is degenerate for a one-part override
  (PR.IR-03, `missing_parts: [1]`): any Gap or Partly covered on that part counts as agreement, so do not over-read
  it (R5);
- every key change since the first baseline (Ruling 11), including judge 2's four changes, PR.DS-11's fallback, and
  the per-part re-judge (PR.DS-02 Partly covered, with two lmp lines registered);
- each miss with its parts' labels;
- for every expected-Gap outcome, the part (if any) that cited a line, and which line (adversary I1);
- the stance requests the run made (73; the record run makes 72 live calls, R6) and the cost and seconds per core
  run, against today's $0.0333 and 378 s (I5);
- the known risks:
  - RS.CO-02: a scope over-read, accepted as a miss;
  - PR.AA-01: the Okta row may read as no on the users part (Ruling 11d);
  - PR.DS-01: its integrity part rests on a monitoring line (lmp line 9), the judge's weakest;
  - PR.IR-03: "in normal and adverse situations" is a pair and stays in its one part;
  - RC.RP-01: its one part carries "once initiated from the incident response process", which round 2's stance read
    as a requirement bcp:30 does not state (likely Gap against an expected Covered);
  - RS.MA-01: its one part carries both qualifiers (third parties, once declared) and may read as Gap against an
    expected Partly covered.

**Minors** (adversary checkpoint 2; Ruling 17 leaves them to the drafter):
- M1, done: `explain` shows every disagreeing part with its own template answer, so each part's conflict is shown.
- M2, done: the citation dedupe key includes stance (tested).
- M3, done: GV.PO-02 parts 3-4 now follow NIST ("communicated", "enforced to reflect ..."); part 3 shares GV.PO-01
  part 2's text and recording key (noted in Step 2).
- M4, done: the spec no longer claims the explanation passes the answer check. The PR.DS-01 test checks that every
  quote in the explanation is cited. The group line's part numbers are code's text, not evidence.
- M5, partly done: the spec notes what `retrieval_recall_at_8` and the seconds now measure. **Skipped:** renaming the
  metric, which would change the results files and both packs' report code for no new information.
- M6, done: `test_a_changed_tier_list_gives_a_new_questionnaire` changes one part only.
- M7, partly done: `_without_draft`'s docstring names the test that pins it. **Skipped:** the `Literal` step type,
  because `Spend` is a frozen contract (`Callable[[str], bool]`) and narrowing it is a rule-10 change.
- M8, **skipped in 6A**: showing a draft-only quote's document status belongs to 6B's inspector, so it is carry (d)
  in Step 1.
- M9, done: spec section 6 gets its sentence.
- M10, done: the explanation lists part numbers by group, then the deciding parts' questions with their answers.
- M11, done: the disagreement fixture cites its own no line.
- M12, done: `PartLabel` types `combine`, `_DECIDE`, `PART_WORDS` and `_DECIDING`.
- R3 (recheck), done: the example clause ends at the next comma or the question mark (tested).
- R4 (recheck), done: a `paraphrase_words` entry in the old list form is named, not a crash (tested).
- R5 (recheck), done: Step 14 notes that `part_agreement` is degenerate for the one-part override (PR.IR-03).
- R6 (recheck), done: Steps 1 and 13 say a record run makes 72 live calls for 73 stance requests.
- I2's "part count in the key file header", **skipped**: a re-cut already shows in `git diff` twice, in
  `tiers.yaml` (with the required change-log line) and in `gap-dev.json`'s per-part report. A header in a file that
  `dump_yaml` writes would need a `Key` schema change.

## Self-review notes (for the lead)

- **Spec coverage.** Section 4: Task 1 (file, fields, verbatim NIST text, drift test, refresh rule, tiers fixed with Tarun). Section 5: steps 2-5 in Tasks 3-4 (`check_outcome`, gap labels, `ask_queue` + `store_statement`, not-checked makes no call); step 1 (the view starting a run, caps, expiry) and step 6 (re-check after an upload or answer) are HTTP flows, deferred to 6B with Plan 3's runner (`recheck` is reused unchanged). Section 6: Tasks 2 and 4. Section 7: 6B. Section 8: Tasks 5-7, every gate in the table (cost and speed reported), fail-closed, CI replay, eval key. Section 9: Ask-me answers redacted by `store_statement` and measured by the redaction gate; the CSF file is read, never fetched or executed. Section 11: Tarun's approvals of the IDs (Task 1 Step 7) and of the first baseline (Task 7 Step 5); README and view are 6B.
- **Type consistency.** `gap_label(o, label, value=None, statement_id=None)` is called the same way in Tasks 3, 4, 5 and 6; `questionnaire_for`, `check_outcome`, `ask_queue`, `item_input` keep Task 4's signatures in Task 6; `datakit.gap.doc_path(pack, gap, spec)` and `trap_sources(f, control)` match their uses in `evals/gap.py`; `score.gates(metrics, table)` is the one signature change in `evals/score.py`.
- **Counts that tests pin and that move together:** 106 outcomes, 31 Checked, 5 Ask-me, 70 not checked, 36 in the core, 7 in Govern, 73 parts; expected 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree, 3 Gap. If Tarun changes the tiers at the review gate, update these numbers in `tests/datakit/test_csf.py`, `tests/test_csf.py`, `tests/datakit/test_gap.py` and `tests/test_eval_gap.py` together with the outcome map.
