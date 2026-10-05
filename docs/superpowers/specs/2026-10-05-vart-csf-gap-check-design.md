# VART: CSF 2.0 gap check — design spec

_Date: 2026-10-05 · Status: draft for Tarun's review · Owner: Tarun Theegela · Lead agent: Claude Opus 5.5 ·
Builds on: `2026-10-03-vart-v2-design.md` (the main spec; its hard rules, section 3, bind this feature too)_

VART answers vendor security questionnaires from a company's own documents, with every answer cited and every label
decided by code. The gap check points the same engine at a public framework instead of a buyer's questionnaire: it
reads the company's documents against NIST's Cybersecurity Framework (CSF) 2.0 and reports, outcome by outcome, what
the documents show is in place, what they show is not, where they disagree, and what they never mention. Each finding
quotes the company's own line and NIST's own text, with a link to the official source.

---

## 1. Why

- Tarun's goal (2026-10-05): when a company's documents show something that does not meet a regulation or framework,
  VART should say so, explain the conflict, and back it with sources and links. Free sources only.
- Vendors are asked "are you aligned with NIST CSF?" constantly; today they answer by hand. A cited, code-labelled gap
  report is the same trust story VART already tells for questionnaires.
- Portfolio value: one hardened engine (retrieval, stance, decide, redaction, evals) serves both questionnaires and a
  regulation check, with no new labelling logic.

## 2. Decisions (brainstorm, 2026-10-05)

| Question | Decision |
|---|---|
| Which framework first | NIST CSF 2.0, with each outcome's related NIST SP 800-53 rev5 controls shown as links. Both are US government works (public domain). |
| Where results appear | A separate **Gap check** view next to the questionnaire run. |
| How it works | Approach A: each CSF outcome becomes a fixed built-in question, run through the existing `answer_item` pipeline unchanged. |
| Which outcomes | All ~106 CSF 2.0 outcomes are stored. v1 checks a curated core of about 30 against documents (**Checked**), asks the visitor about about 5 (**Ask me**), and lists the rest as **Not checked yet**. The visitor can run the whole core or one CSF function. |
| Source format | One bundled JSON file, downloaded from NIST once and committed. No runtime API, no RAG over CSF (the run walks every outcome in scope; there is nothing to search). Retrieval (RAG) runs over the company's documents, as today. Google's Open Knowledge Format was considered; an OKF export can come later if the data needs to be shared with other agents. |
| Legal framing | Never legal advice. Every finding reads "possible gap, review it"; the view and the export say so. |
| Not chosen | regulations.gov (proposed rules and comment dockets, not codified rules: a later "rules coming soon" feed at most); paid frameworks (SOC 2 criteria, ISO 27001 text); per-passage classification (approach B) and a single model review (approach C, which breaks "code decides labels"). |

## 3. Scope

**In v1:** the CSF data file and its drift test; the built-in CSF questionnaire (one migration); the Checked and Ask-me tiers; the Gap check
view in design direction C; the gap report in the existing export; the gap-check eval pack, key and gates.

**Out of v1:** other frameworks (HIPAA Security Rule, FTC Safeguards Rule, GDPR are the next candidates, all free via
eCFR or EUR-Lex); outcomes beyond the core; any statement of legal compliance; regulations.gov; OKF export.

**Depends on:** Plan 2 (engine, ingest, evals) released and Plan 3 (API and UI) built. This becomes its own plan after
Plan 3; it adds no schema change that Plans 2-3 must anticipate beyond what section 6 lists.

## 4. Data: `data/csf/csf-2.0.json`

Downloaded once by hand from NIST's CSF 2.0 reference data (the Cybersecurity and Privacy Reference Tool export,
including the informative references to SP 800-53 rev5), trimmed, and committed with the download date. The app never
fetches it.

One entry per CSF 2.0 outcome (subcategory):

| Field | Example | Owner |
|---|---|---|
| `id` | `PR.AA-05` | NIST |
| `function`, `category` | `Protect`, `Identity Management, Authentication, and Access Control` | NIST |
| `outcome` | the outcome text, verbatim | NIST |
| `related_controls` | `["AC-2", "AC-3", "AC-6"]` | NIST's mapping |
| `source_url` | NIST's page for the outcome | NIST |
| `tier` | `checked`, `ask`, or `not_checked` | VART |
| `question` | a fixed retrieval-friendly phrasing (checked and ask tiers only) | VART |
| `csf_version`, `retrieved` | `2.0`, the download date | VART |

Rules:
- What the visitor sees as "the framework" is always NIST's verbatim `outcome` text. Only `question` and `tier` are
  VART's.
- A unit test re-reads the committed NIST source extract and fails if any `id`, `outcome`, `related_controls` or URL
  differs, or if a control ID is not a valid SP 800-53 rev5 identifier.
- Refreshing the file is a deliberate change with a new `retrieved` date, a re-run of the eval and a change-log line.

**v1 tiers (the exact IDs are fixed in the plan's first task, from the downloaded file, for Tarun's review):**
- **Checked (about 30):** outcomes a vendor's policies and records state directly — Protect: identity, authentication
  and access control; data security; platform security; technology infrastructure resilience. Detect: continuous
  monitoring and adverse event analysis. Respond: incident management, analysis, reporting and mitigation. Recover:
  incident recovery plan execution. Identify: asset management basics. Govern: policy (GV.PO).
- **Ask me (about 5), all Govern:** risk appetite and tolerance (GV.RM); roles and responsibilities (GV.RR); supply-
  chain risk management (GV.SC); legal and regulatory requirements understood and managed (GV.OC); leadership oversight
  of cybersecurity risk (GV.OV).
- **Not checked yet:** the rest (about 71). Moving an outcome into Checked is a data change plus answer-key entries;
  the eval proves it, no code changes.

## 5. Run flow

1. In the Gap check view the visitor picks the scope — the whole core, or one CSF function — and starts a run (key `r`).
   It creates (or reuses) the workspace's built-in CSF questionnaire for that scope and starts an ordinary run with the same run machinery, per-run and per-IP budget caps, and expiry
   as questionnaire runs.
2. **Checked outcomes** run through `answer_item` unchanged, with the outcome's `question` as the item text:
   retrieve the top passages from the uploaded and sample documents → stance per passage (yes / no / partial, with the
   whole quoted sentence) → decide (code, spec 6.7 unchanged) → draft a one-to-two sentence explanation, checked
   against its quotes.
3. **Gap labels** are a display mapping over decide's output (decide itself does not change):

   | Decide output | Gap check label | Meaning |
   |---|---|---|
   | `verified`, value Yes | **Covered** | the documents show the outcome is in place |
   | `partial` | **Partly covered** | some evidence, a negated yes, a draft-only source, or a narrower scope |
   | `verified`, value No | **Not met (stated)** | the documents themselves say it is not done or only planned: the non-compliance alert |
   | `conflict` | **Documents disagree** | e.g. the policy says quarterly reviews, the log shows them overdue |
   | `unknown` | **Gap** | no usable evidence in the documents |

4. **Ask-me outcomes** skip retrieval and go to *Questions for you*. An answer is redacted, stored as a statement
   (`store_statement`) and shown as **Confirmed by you**, citing the statement; unanswered ones show **Not answered**.
   A later upload re-checks them through the existing `recheck`.
5. **Not-checked outcomes** make no model call and carry no label: they show NIST's text, links and "not checked in this
   version".
6. **Re-check:** a new upload or an answered question re-runs only the affected outcomes, as for questionnaires.
7. **Cost:** about 35 outcomes per full-core run, below a 60-item questionnaire run; it uses the existing caps.

## 6. Data model

The schema already fits: runs belong to a questionnaire, and `items.csf_id` exists.
- A gap check is a built-in questionnaire per workspace: `questionnaires.source = 'csf'` (one new allowed value in
  `ck_questionnaires_source`, one migration), `filename` = `csf-2.0`, and `mapping` records the CSF data version and the
  chosen scope (`core` or a function name).
- Its items are ordinary `items` rows: `question` = the outcome's `question`, `code` = the CSF `id`, `csf_id` = the CSF
  `id`, `topic` = the CSF category. Runs, run items and answers are unchanged, including the `ck_answers_cited`
  constraint (no Covered or Partly result without a citation).
- The CSF data file is read-only reference data, not stored in the database beyond the items a run creates.

## 7. View (design direction C, `design.md`)

- New tab `6 gap check` in the top bar.
- Command line: path `<company> / csf 2.0 / <scope>`; scope keys `g i p d s o` (Govern, Identify, Protect, Detect,
  Respond, Recover) and `a` (all core); `r` run; `e` export.
- Filter line with counts per label: covered, partly, not met, disagree, gap, confirmed by you, not answered, not
  checked. Each label keeps C's word-plus-border styling (monochrome only).
- One 28px line per outcome, grouped `# protect / identity, authentication & access control`: id, label, sources,
  NIST outcome (shortened), VART's one-line explanation.
- Inspector drawer: label; NIST's verbatim outcome with its link; related 800-53 controls as links; VART's explanation
  with footnoted sources; each cited line in the line listing; dropped evidence. For an Ask-me outcome: the question
  and an answer box.
- Status line: `checked 30 · ask me 5 · not checked 71 · of 106` so coverage is never overstated.
- Export: the existing xlsx export gains a gap-report sheet: id, function, category, label, explanation, quotes with
  file and line, NIST text, links, related controls, run date, CSF version.
- Copy: "Possible gap — review it" and a footer line "Not legal advice. CSF 2.0 text © NIST, public domain."

## 8. Evals

A new eval pack, `gap-dev`, over the existing dev company documents (no new documents unless an outcome needs one).

**Answer key.** One expected label per Checked outcome with the quote that proves it, derived by code from the dev
pack's fact sheet (`datakit` key derivation, as for questionnaires): nobody hand-writes answers to match the engine.
Planted on purpose: at least two **Documents disagree** outcomes, at least two **Not met (stated)** outcomes, at least
two honest **Gaps**, and trap outcomes where only a template, a draft or a planned-only sentence mentions the control.

**Gates** (tightened after the first baseline to max(spec value, baseline - 0.02), as in the main spec):

| Gate | Rule |
|---|---|
| Cited coverage | every Covered and Partly result cites a line that contains its quote: 1.00 |
| Trap coverage | a template, draft-only or planned-only source never yields Covered: 0 |
| Label accuracy | on Checked outcomes: ≥ 0.80 |
| Disagreements caught | recall on planted Documents-disagree outcomes: 1.0 |
| Stated non-compliance | recall on planted Not-met outcomes: 1.0 |
| NIST text intact | unit test, section 4: all pass |
| Honest tiers | Not-checked outcomes carry no label; Ask-me labels come only from a stored statement: all pass |
| Redaction | names and secrets in Ask-me answers never reach a model (existing leak scan): 0 |
| Cost and speed | USD and p50 seconds per full-core run: reported |

Every gate fails closed when it has nothing to measure. CI replays recorded model outputs; recording uses the capped
eval key.

## 9. Security and privacy

Everything in the main spec's section 9 applies unchanged: uploads and Ask-me answers are redacted before any model
call; injected text never reaches a model; per-workspace and per-IP limits apply. The CSF file is trusted reference
data, committed and tested; nothing from it is executed. NIST text is quoted, not paraphrased, and attributed.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Visitors read a gap report as a compliance verdict | "Possible gap — review it" wording, coverage line, not-legal-advice footer, no overall score |
| A fixed question phrasing misses evidence worded differently | retrieval recall is measured on the gap pack; phrasings are tuned within the plan's tuning rules, never per document |
| NIST revises CSF | the file carries its version and date; refresh is deliberate and re-runs the evals |
| Outcomes are broad, documents are specific | Partly covered is the honest default for partial evidence; the explanation names what is missing |

## 11. Definition of done

The data file and its drift test; the built-in CSF questionnaire; the view and export; the `gap-dev` pack, key and gates all
green on replay; the README explains what the gap check is and is not; Tarun approves the tiers' exact IDs and the
first baseline.
