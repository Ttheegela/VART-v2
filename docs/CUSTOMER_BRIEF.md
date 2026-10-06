# Customer brief

Who VART is for, the problem it addresses, and what would show it works. The success statements are hypotheses to
test with real users, not results.

## Who
The security or compliance lead, or the sales engineer, at a 20 to 200 person B2B (business-to-business: sells to other
companies) software company. Enterprise buyers send them a security questionnaire (their own spreadsheet, or a
standard one such as CAIQ, the Cloud Security Alliance's; HECVAT, higher education's; or SIG, Shared Assessments')
before a deal can close.

## The problem
Each questionnaire takes one to three days. The answers are scattered across policies, audit reports, penetration
test reports and spreadsheets, and those sources sometimes disagree: a policy says access is reviewed quarterly, the
access-review sheet shows the last review nine months ago. A missed contradiction becomes an audit finding or lost
buyer trust. An invented answer is worse.

## What success looks like for them (hypotheses)
- Most items arrive pre-answered with a citation they can check.
- Contradictions between documents are found before the buyer finds them.
- A person spends time only on real gaps, answering "Questions for you" once.
- The filled file goes back in the buyer's own format.

## Success metric
A visitor fills the sample questionnaire in under a minute with no signup, and every answer carries a citation that
can be checked. This is measured by evals (automatic scored tests of the answers) that run in CI (the checks that
run automatically on every change to the code):
- Citation validity: every quote shown really appears in the document it cites. The target is every one, 1.00.
- Every contradiction planted in the test company's documents is caught.
- On the dev pack (the sample company used while building and tuning), the share of labels that match the answer key
  stays above a gate (a threshold that fails the build when it is missed).
- No instruction hidden in a document is followed.
The holdout pack is a second company authored in parallel and first run after the engine was frozen, so nothing could be tuned on it; its
results are reported, not tuned.

## Out of scope
A reusable answer library across questionnaires; several users, roles, single sign-on, Slack routing, ticketing;
scanned PDFs with no text layer (rejected with a message); real compliance use. This is a demo on synthetic data:
do not upload confidential documents. VART drafts answers for a person to check; it is not legal or
compliance advice.
