# VART

Fills a vendor security questionnaire from a company's own documents. Every answer cites the exact passage it came
from, contradictions between documents are flagged instead of guessed, and a person is asked only what the documents
do not cover.

Status: live at https://vart-v2.vercel.app (Plans 1-3, 6). Design: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`.

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
