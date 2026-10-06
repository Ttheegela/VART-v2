# VART

Fills a vendor security questionnaire from a company's own documents. Every answer cites the exact passage it came
from, contradictions between documents are flagged instead of guessed, and a person is asked only what the documents
do not cover.

Status: live at https://vart-v2.vercel.app. Design: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`.

## The problem

At a 20 to 200 person B2B SaaS company, the security or compliance lead (or the sales engineer) gets a security
questionnaire from every enterprise buyer, and each one takes one to three days. The answers are scattered across
policies, audit reports, pentest reports and spreadsheets, and those sources sometimes disagree: a policy says access
is reviewed quarterly, the access-review sheet shows the last review nine months ago. A missed contradiction becomes
an audit finding or lost buyer trust, and an invented answer is worse.

<!-- demo.gif: 1280x720 browser window, 12-15 fps, at most 45 s and 8 MB, saved as docs/demo.gif.
0-4 s Home: press `s` ("Try with a sample company").
4-9 s The grid fills at once ("64 of 64 answered · done · precomputed sample answers"); the tour's first card shows, then Skip (Esc).
9-16 s Press `v` (verified), Enter on a row: the evidence drawer with the quote highlighted in its document.
16-23 s Escape, press `c` (conflict), Enter: both sides with their dates.
23-32 s Press `3` (Questions for you), answer one question, Send: "confirmed by you" and suggested fills.
32-40 s Press `6` (gap check): Covered, Partly covered, Not met, Gap; open PR.DS-11's parts.
40-45 s Press `e` (export): the filled workbook downloads. -->
![VART filling the sample questionnaire](docs/demo.gif)

Live: https://vart-v2.vercel.app. "Try with a sample company" is instant and needs no signup or key.

## How it works

Retrieve passages (Postgres full-text search, no pinned evidence), ask a model each passage's stance on the question,
**decide** the label in code (quote containment, template gate, negation, date rule, conflicts, draft ceiling), then
draft the answer and check it against its quotes. A person is asked only what the documents do not cover (the
interview): an answer becomes a dated statement used as evidence, and suggests fills for other open items. The export
writes the answers back into the buyer's own spreadsheet. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Results

Copied from `evals/results/latest.md` (dev pack) and `evals/results/holdout.md` (a second company, authored in
parallel and first run after the engine was frozen; reported, not tuned; one engine change landed after the tag: cf9d696 (adversary-2 M6), which makes the PDF inexact-page path fail closed and is likely unreachable; the dev, gap-dev and holdout replays are byte-identical after it, so nothing was re-recorded). All gates and the model bench are in
[`docs/EVALS.md`](docs/EVALS.md).

| Metric | Target | Dev | Holdout |
|---|---|---|---|
| label_accuracy | >= 0.9 | 0.9326 | 0.8539 (below target) |
| conflict_recall | >= 1.0 | 1.0 | 0.7143 (below target) |
| citations_valid | >= 1.0 | 1.0 | 1.0 |
| injections_followed | <= 0.0 | 0.0 | 0.0 |
| judge_faithfulness | >= 0.95 | 0.971 | 0.973 |
| cost per 60 items (USD) | reported | 0.0335 | 0.0594 |

A live 64-item run took 231 s in 16 steps and cost $0.0622, measured locally (FastAPI TestClient, live models), not on Vercel. Before, steps ran items one at a time: an
estimated 11 minutes (64 items x the 10.35 s p50, sequential), so about 3 times faster against that estimate. The gap check's label accuracy is 0.7097 against a 0.80 target (reported below
target, accepted 2026-10-06).

**One definition changed after the first holdout score.** `injections_followed` first read 1.0 (a count: 1 of 2 traps) because
the scorer counted a trap whose text never reached the model. Tarun decided to redefine it: *followed* now means the
target's label differs from the key and the trap reached the target, and the gate fails closed. The holdout value
became 0.0 (0 of 2). Nothing was re-recorded, and the dev results did not change. See `docs/EVALS.md`.

## v1 and v2, honestly

v1 was a one-day hackathon build (Money Talks AI x Finance Hackathon, 2026-09-05) on a sponsor's private document
pack, run from local scripts, with no public demo. v2 is a solo rebuild on public questionnaires and synthetic company
packs, with a live app, an export back into the buyer's file, and evals in CI. The numbers are not like for like: the
data differ, and v1's retrieval pinned the answer key's evidence ahead of the search results, so its retrieval
numbers flatter it (its label accuracy before the interview was 0.515 and 0.545). v2 pins nothing.

## Engineering

- Tests and evals run in CI on every push; the dev, gap-dev and holdout evals replay recorded model outputs and CI
  fails on drift. Model calls are recorded and replayed, so tests never touch the network.
- Per-network and global call budgets, upload limits, PII and secret redaction before storage and before any model
  call, Langfuse tracing (metadata only), `/api/health`, a daily canary and UptimeRobot monitors.
- Browsers: Chromium-based browsers (Chrome, Brave, Comet, Edge) are covered by the Chromium tests; Safari by the
  WebKit tests and a manual check on the Mac and an iPhone at each release; Firefox is untested.
- More: [`docs/SECURITY.md`](docs/SECURITY.md), [`docs/RUNBOOK.md`](docs/RUNBOOK.md),
  [`docs/CUSTOMER_BRIEF.md`](docs/CUSTOMER_BRIEF.md), [`docs/LEARNING.md`](docs/LEARNING.md).

## Run it locally

```
docker compose up -d db
export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test && export DATABASE_URL=$TEST_DATABASE_URL
ruff check . && ruff format --check . && mypy app scripts datakit && pytest -q && alembic check
cd web && npm run lint && npm test && npm run build
python -m evals.run --pack dev        # replay, no network or key
```

Code is MIT-licensed. Files under `data/` carry their own licenses: the terms are in `data/LICENSE`, the attributions
in `data/NOTICE.md`.

## Gap check (NIST CSF 2.0)

**What it is.** VART reads your documents against NIST's Cybersecurity Framework 2.0 and reports, outcome by
outcome, what they show: **Covered**, **Partly covered**, **Not met (stated)** when a document says a part is not
done, **Documents disagree**, or **Gap** when nothing speaks to it. Each checked outcome is cut into NIST's own
parts; every part is asked as a question through the same engine that fills questionnaires, and code combines
the parts' labels and writes the explanation. Every finding quotes your line next to NIST's verbatim text and
links to NIST, with the related SP 800-53 Rev 5 controls. The report exports as a gap-report sheet, alone or
inside your filled questionnaire. The sample company's documents include an improvement plan that states two
controls are not in place yet, so the demo shows what a stated non-compliance looks like: the sample company is
not compliant with those two controls, by design.

**What it is not.** It is not legal advice, an audit, a certification or a compliance score, and no overall score
is shown. Every finding reads "possible gap, review it". It checks 31 of CSF 2.0's 106 outcomes against documents,
asks you about 5 governance outcomes that documents rarely state, and lists the other 70 as not checked in this
version. The coverage line counts outcomes by tier, not parts: 31 checked against documents in this version, 5 asked
of you, 70 not checked, of 106. The "n of 31 checked" beside it counts only Checked outcomes with a result; an
Ask-me, failed or not-applicable outcome never counts there. A checked outcome is judged on documents only: your
answers to the Ask-me outcomes read "Answered by you" (an answer, not a verdict), and can fill a checked part in the
same CSF function only as a suggestion you accept. On the dev pack its outcome labels agree with a blind judge's
key 22 times in 31 (0.71 against a 0.80 target, reported in `evals/results/gap-dev.md`).

Not legal advice. CSF 2.0 text © NIST, public domain.
