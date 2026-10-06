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
| How it works | Approach A, per part (amended 2026-10-06). Each Checked outcome is cut into its NIST **parts** by a fixed rule (section 4), and the parts are stored as data in `data/csf/tiers.yaml`. Each part runs as a fixed built-in question through the existing pipeline, unchanged: retrieve, stance, decide. Code then combines the parts' labels into the outcome's label (5.3). Why: with one question per outcome, stance could not tell a line that answers one part from a line that answers all of them, and a union of part-lines could never reach Covered (gap-tune-2 diagnosis). |
| Which outcomes | All ~106 CSF 2.0 outcomes are stored. v1 checks a curated core of about 30 against documents (**Checked**), asks the visitor about about 5 (**Ask me**), and lists the rest as **Not checked yet**. The visitor can run the whole core or one CSF function. |
| Source format | One bundled JSON file, downloaded from NIST once and committed. No runtime API, no RAG over CSF (the run walks every outcome in scope; there is nothing to search). Retrieval (RAG) runs over the company's documents, as today. Google's Open Knowledge Format was considered; an OKF export can come later if the data needs to be shared with other agents. |
| Legal framing | Never legal advice. Every finding reads "possible gap, review it"; the view and the export say so. |
| Not chosen | regulations.gov (proposed rules and comment dockets, not codified rules: at most a later "rules coming soon" feed); paid frameworks (SOC 2 criteria, ISO 27001 text); per-passage classification (approach B); a single model review (approach C, which breaks "code decides labels"). For parts-aware labels (2026-10-06), also not chosen: a cap that lowers Covered over one question (it only lowers labels and cannot build Covered from separate lines); a shared stance-prompt change (it risks the dev pack's 0.90 gate and cannot build Covered from separate lines either). |

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
| `parts` | `["Are backups of data created?", "Are backups of data protected?", ...]`: the outcome cut by the rule below, as yes/no questions in NIST's order (Checked tier only, at least one) | VART |
| `csf_version`, `retrieved` | `2.0`, the download date | VART |

Sync (Plan 6A, Task 7): the version, the date and the source are stored once at the top of the file, not on every
entry. The controls are SP 800-53 Rev 5.2.0. `source_url` is the Reference Tool page (NIST has no page per outcome).
The tier change log is the comment block at the top of `data/csf/tiers.yaml`.

Rules:
- What the visitor sees as "the framework" is always NIST's verbatim `outcome` text. Only `tier`, `question` and
  `parts` are VART's.
- **The cut**, which uses NIST's text only and is the same for every outcome:
  1. Every verb in a list of verbs is a part ("reviewed, updated, communicated, and enforced" gives four parts). So
     is every gerund in such a list ("receiving, analyzing, and responding").
  2. In a sentence with one verb, a comma list of three or more nouns is cut wherever it stands, one part per item
     ("software, services, and systems"). That includes a list inside a qualifier ("based on classification,
     criticality, resources, and impact on the mission" gives four parts); the qualifier's other words stay on every
     part. In a sentence with a list of verbs, the nouns are not cut.
  3. A pair of nouns joined by "and" is never cut ("identities and credentials", "hardware and software", "internal
     and external stakeholders").
  4. A qualifier is never a part of its own, and apart from rule 2's lists it is never cut. A qualifier is a phrase that says how, when, from where
     or why ("based on ...", "commensurate with risk", "to reflect changes in ...", "in normal and adverse
     situations", "once ...", "in coordination with ..."). It stays on the verb it follows in NIST's text.
  5. A second predicate ("and incorporate the principles of ...") is cut by the same rules.
  6. There are no exceptions.
- **Wording.** A part uses NIST's words for its outcome (the outcome and category text) plus question words. Any
  other word may appear only inside an example clause ("such as ...", "for example ...") and must be listed for that
  outcome in `paraphrase_words`, mapped to the word of NIST's text it is an instance of (`encryption: protected`).
  An outcome has at most three such words. A part never adds a requirement, a document name or a quote. Every word
  of NIST's outcome appears in at least one part. `python -m datakit.validate csf` fails otherwise.
- **The parts are frozen once recorded.** After the first gap-dev recording under parts, any change to a part counts
  as a tuning round under the plan's rules: adding, removing, merging, splitting or rewording one. Each change needs
  a `tiers.yaml` change-log line that cites the NIST clause, and the baseline report lists it. A re-cut also shows in
  the per-part report of `evals/results/gap-dev.json`.
- A unit test re-reads the committed NIST source extract and fails if any `id`, `outcome`, `related_controls` or URL
  differs, or if a control ID is not a valid SP 800-53 rev5 identifier.
- Refreshing the file is a deliberate change with a new `retrieved` date, a re-run of the eval and a change-log line.

**v1 tiers (the exact IDs are fixed in the plan's first task, from the downloaded file, for Tarun's review).**
Sync: the approved list is 31 Checked, 5 Ask me and 70 not checked (Tarun added RS.AN-03 and RS.MI-01 at the tier
gate on 2026-10-05); the "about" counts below are the first draft.
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
2. **Checked outcomes run part by part.** For each part, in order, the part's text is the item text and the CSF
   category is the topic. The pipeline retrieves the top passages from the uploaded and sample documents, drops any
   stored statement (Ruling 9), takes a stance per passage (yes / no / partial, quoting the whole sentence) and runs
   decide (code, spec 6.7 unchanged). This is `answer_retrieved`, unchanged. A part's own draft is refused before it
   is spent, so it makes no model call and costs nothing; the outcome's explanation is written by code (step 3). The
   budget is spent before every stance call, and no database transaction is open while a model runs. The parts'
   own results stay available to the caller (`check_parts`) for diagnosis, the inspector and re-check.

Replace step 3 with:

3. **Gap labels.** Each part's decide output maps through this table (decide itself does not change):

   | Decide output | Gap check label | Meaning |
   |---|---|---|
   | `verified`, value Yes | **Covered** | the documents show the outcome is in place |
   | `partial` | **Partly covered** | some evidence, a negated yes, a draft-only source, or a narrower scope |
   | `verified`, value No | **Not met (stated)** | the documents themselves say it is not done or only planned: the non-compliance alert |
   | `conflict` | **Documents disagree** | e.g. the policy says quarterly reviews, the log shows them overdue |
   | `unknown` | **Gap** | no usable evidence in the documents |

   The outcome's label combines its parts' labels in code. The first rule that applies wins:

   1. **Documents disagree**: any part is Documents disagree. Until a person says which document is current, no other
      label is safe to show, and Ruling 15 ranks a real final-vs-final conflict above missing parts. The explanation
      still names any part stated as not done.
   2. **Not met (stated)**: any part is Not met (a verified No). If a document says one part is not done, the outcome
      is not met, however well its other parts are evidenced. Partly covered would hide the non-compliance alert.
      Only a stated No counts: a part that is partial with a no line in it stays Partly covered.
   3. **Covered**: every part is Covered. Every clause of the outcome has a final, verified yes.
   4. **Gap**: every part is Gap. Nothing in the documents speaks to any clause.
   5. **Partly covered**: any other mix, for example yes with unknown, or any partial part.

   For an outcome with one part, the result is that part's label, so the table above is the single-part case.

   **The outcome's Decision is a display record.** Its label and value come from the combination above. Its
   citations are the union of the parts' citations in part order, with duplicates removed (same document, lines,
   quote and stance). Each citation keeps the stance its own part judged it with (`Citation.stance`), so 6B shows
   the stance next to the quote. Because of this, the record does not satisfy decide's per-label rule: a Not met
   outcome can carry the yes citations of its evidenced parts.

   The citations rule (`ck_answers_cited`) still holds. Every outcome that is Covered, Partly covered, Not met or
   Documents disagree has at least one part that decide did not label unknown, and decide gives such a part at
   least one citation. So no Covered or Partly result is ever stored without a citation. A Gap outcome cites nothing.

   **The explanation is written by code, with no model call.** It has two pieces:
   - Groups of part numbers by label: "Evidenced: parts 1, 2. Stated as not done: part 3."
   - For each part that decided the outcome's label, that part's question followed by its own template answer
     (`app.draft.template_answer` over the part's own Decision). For Documents disagree, these are the disagreeing
     parts. For Not met, the stated-No parts. For Covered, every part. For Partly covered, the Covered and Partly
     covered parts. For Gap, there are none.

   This way a quote always stands next to the stance it was judged with, a "No." is never printed over yes lines,
   and every disagreeing part's sides are shown. The quotes are cited lines. The explanation is code's text and is
   not passed through the draft answer check.

   One draft call per outcome was not chosen, for three reasons:
   - The draft prompt cannot name parts without changing, and that change is frozen and would mean re-recording the
     dev pack.
   - The part labels are already known exactly in code.
   - The call is cheap but not free: about $0.003 and 70 s per core run.

4. **Ask-me outcomes** skip retrieval and go to *Questions for you*. An answer is redacted, stored as a statement
   (`store_statement`) and shown as **Confirmed by you**, citing the statement; unanswered ones show **Not answered**.
   A later upload re-checks them through the existing `recheck`.
5. **Not-checked outcomes** make no model call and carry no label: they show NIST's text, links and "not checked in this
   version".
6. **Re-check:** a new upload or an answered question re-runs only the affected outcomes, as for questionnaires, and
   for a Checked outcome it runs per part (Plan 6B builds it):
   - The interview re-check takes one open item per part (key `<id>#<n>`) with that part's label. A part is open
     when it is Gap, Partly covered or Documents disagree.
   - A suggestion is for one part. Accepting it replaces that part's result, then re-runs the combination and the
     explanation; it never replaces the outcome's Decision directly.
   - A new upload re-runs every part of the affected outcomes.
7. **Cost and the runner:**
   - **Size.** The core's 31 Checked outcomes have 73 parts. A full core run therefore makes at most 73 stance calls,
     one per part with passages, and no draft calls. Parts with identical text share a recorded reply, so the eval's
     record run makes 72 live calls.
   - **Price and time.** At the eval models' recorded prices ($0.0010 and 10.4 s per stance call, p90 15 s), that
     is about $0.07 and about 13 minutes, run one after another.
   - **The hourly cap.** The per-workspace hourly stance cap is 150, and a core run uses about half of it. One core
     run plus a 60-item questionnaire run is 133 calls. A second core run, or a re-check, in the same hour can be
     refused partway: `answer_retrieved` raises `BudgetExhausted` inside an outcome, and the parts already paid for
     are lost unless they are kept. The caps do not change. Plan 6B stores each part's result as it lands, so a
     step resumed in the next hour re-runs only the unpaid parts.
   - **Claiming items.** A step claims csf items until their parts add up to 8 or fewer. That is 8 x 15 s = 120 s at
     p90, inside the step's 240 s deadline (spec 6.3). An outcome with more than 8 parts would be claimed alone; no
     v1 outcome has more than 5.

Sync (Plan 6A, Task 7), 5.3: `na` shows no label. A Checked outcome the visitor confirms shows **Confirmed by you**.
Sync, 5.4: *Questions for you* holds Ask-me outcomes only.

## 6. Data model

The schema already fits: runs belong to a questionnaire, and `items.csf_id` exists.
- A gap check is a built-in questionnaire per workspace: `questionnaires.source = 'csf'` (one new allowed value in
  `ck_questionnaires_source`, one migration), `filename` = `csf-2.0`, and `mapping` records the CSF data version and the
  chosen scope (`core` or a function name).
- Its items are ordinary `items` rows: `question` = the outcome's `question`, `code` = the CSF `id`, `csf_id` = the CSF
  `id`, `topic` = the CSF category. Runs, run items and answers are unchanged, including the `ck_answers_cited`
  constraint (no Covered or Partly result without a citation).
- Items keep the outcome's `question`. The parts live only in the CSF data file and are covered by the
  questionnaire's digest: a changed part gives the next run a new questionnaire. There is no parts table.
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

**Answer key.** The key holds one expected label per Checked outcome, at the outcome level, with the quotes that
prove it. Code derives it from the dev pack's fact sheet and its gap extension (`datakit.gap`, using `derive_key`'s
rules), so nobody writes answers to match the engine.

A blind judge may correct the extension's map of an outcome. The judge sees NIST's text, the documents and the fact
sheet, and never the engine's output. If the judge finds the documents cover only some of a broad outcome's parts,
the outcome gets `label: partly_covered`, with `missing:` naming the parts that lack evidence and `missing_parts:`
giving their numbers.

A planted Documents disagree must be visible to the part that asks the question. `datakit.gap` refuses a CSF
conflict whose no side is neither negated nor a record status (for example "performed annually" against "quarterly",
which is a no only against a stated threshold).

The key is never derived through the engine's combination of parts, so a mistake in the precedence rules cannot sit
in both the engine and the key, where the label-accuracy gate could not see it. Nobody edits
`data/dev/key/csf-core.yaml` by hand.

The planted cases stay as they are: at least two **Documents disagree** outcomes, at least two **Not met (stated)**
outcomes, at least two honest **Gaps**, and trap outcomes where only a template, a draft or a planned-only sentence
mentions the control.

**Gates** (tightened after the first baseline to max(spec value, baseline - 0.02), as in the main spec):

| Gate | Rule |
|---|---|
| Cited coverage | every Covered and Partly result cites a line that contains its quote: 1.00 |
| Trap coverage | a template, draft-only or planned-only source never yields Covered: 0 |
| Label accuracy | the outcome's combined label on Checked outcomes: ≥ 0.80 |
| Disagreements caught | recall on planted Documents-disagree outcomes: 1.0 |
| Stated non-compliance | recall on planted Not-met outcomes: 1.0 |
| NIST text intact | unit test, section 4: all pass |
| Honest tiers | Not-checked outcomes carry no label; Ask-me labels come only from a stored statement: all pass |
| Redaction | names and secrets in Ask-me answers never reach a model (existing leak scan): 0 |
| Cost and speed | USD and seconds (the sum of call latencies, one run) per full-core run, every part included: reported |
| Retrieval | `retrieval_recall_at_8` keeps its name and now measures the key quotes found in the union of the parts' passages: reported |
| Part agreement | over the outcomes whose key names `missing_parts`, the share where the engine left every missing part Gap or Partly covered and did not leave all the other parts Gap: reported, not a gate. It is degenerate for a one-part override, where any Gap or Partly covered on that part counts as agreement. |

Sync (Plan 6A, Task 7): the gap extension is `data/dev/gap/` (facts and documents; `python -m datakit.gap dev`),
with the planted cases above, and the gate names are those of `GATES` in `evals/gap.py`. Cost and seconds per core
run are reported.

**Label accuracy is reported, below target (Tarun, 2026-10-06).** The per-part baseline is 0.7097 (22 of 31), under
the 0.80 above. It is accepted and reported, not gating, until a later plan improves stance: `gap-dev.md` keeps the
0.80 target in the table and marks it "reported: below target, accepted 2026-10-06". Every other gate gates.

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
| Outcomes are broad, documents are specific | parts make the breadth explicit: Partly covered when only some parts have evidence, and the explanation names which parts |
| A part adds a requirement NIST does not state, or the parts drop a clause | the csf validate stage fails on any word outside NIST's outcome and category text and the question words, unless it stands in an example clause and is mapped to a NIST word (at most three per outcome). It also fails on any word of NIST's outcome that no part carries. |
| The cut decides labels (a no line in its own part gives Not met; inside a larger part it gives Partly covered) | the cut follows NIST's text by a fixed rule with no exceptions (section 4), and the parts are frozen once recorded: each change is a tuning round with a change-log line that cites NIST |
| A qualifier stays on one verb ("enforced commensurate with risk"), so that part needs a line that states the qualifier | an accepted ceiling: that part's Covered needs the qualifier evidenced. The other verbs' parts do not repeat it, so a missing qualifier lowers one part, not every part. |
| NIST's literal text has parts few companies document. "Availability of data in transit" is almost never a written line, so PR.DS-02 is Partly covered for a company that has only TLS | an accepted ceiling. It is NIST's own text, and the explanation names the part. Nobody tunes a part or the key toward it. |
| A disagreement that is only one interval against another (quarterly vs annually) cannot be seen by a part that states no threshold, and a part may not add one | it is reported in the key's `missing`, not planted as Documents disagree; `datakit.gap` refuses such a planted conflict |
| More parts mean more ways to fall short of Covered, or to pick up a generic line on an expected Gap | Covered needs every part verified Yes, which is the honest bar. The per-part report shows which part cited which line. |
| Cost and time grow with the parts (73 stance calls instead of 31 stance and 25 draft calls) | the parts follow NIST's clauses and nothing more; there is no draft call; the runner claims by parts (5.7) |
| A line read too broadly still answers a part (RS.CO-02: a disaster-recovery role read as incident notification) | a known limit of per-passage stance. It is reported as a miss and not tuned. |

## 11. Definition of done

The data file and its drift test; the built-in CSF questionnaire; the view and export; the `gap-dev` pack, key and gates all
green on replay; the README explains what the gap check is and is not; Tarun approves the tiers' exact IDs and the
first baseline.

## 12. Change log

- 2026-10-06: per-part questions (option A, approved by Tarun; lead Rulings 15 and 17). Sections 2, 4, 5.2, 5.3,
  5.6, 5.7, 6, 8 and 10. Each Checked outcome is cut into NIST parts by a fixed rule. Each part runs through the
  pipeline unchanged, and code combines the parts' labels (disagree, not met, covered, gap, partly) and writes the
  explanation from the deciding parts. decide, stance, the draft prompt, `answer_item` and the dev pack are
  unchanged. gap-dev is re-recorded. The key adopts blind judge 2's changes and its per-part re-judge: PR.DS-11 and
  PR.DS-02 are Partly covered, and the key holds 12 Covered, 12 Partly covered, 2 Not met, 2 Documents disagree and 3
  Gap.
- 2026-10-06: Plan 6A Task 7 sync, no new behaviour. Section 4 (file header, Rev 5.2.0, `source_url`, change log), the
  tiers (31 / 5 / 70), 5.3 (`na`, Confirmed by you), 5.4 and section 8 (gap extension, gate names, cost and seconds).
  Section 8: label accuracy is reported below target (0.7097 against 0.80, accepted by Tarun), not gating.
