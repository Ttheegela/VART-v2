# Security

VART is a public demo on synthetic data. Do not upload confidential documents: use the sample company, or files
you would be happy to see on a public website.

## Reporting a problem
Use GitHub private vulnerability reporting on Ttheegela/VART-v2 (Security tab, "Report a vulnerability"); it is
enabled at release. Until it is on, open a public issue on the repository that only asks for a private contact, with
no details of the problem, and the maintainer will reply with one.

## What is stored, and for how long
- A workspace: its id, when it was made, and a salted hash of the visitor's IP address (`app/db/models.py` Workspace,
  `app/services/ip_limits.py` ip_hash). No account, no name, no email.
- Uploaded documents: the redacted text, line by line, with its chunks; the uploaded bytes are parsed in memory and
  never stored (`app/ingest/store.py`).
- Questionnaires: the original xlsx or csv file, so the export can write answers back into it
  (`app/api/questionnaires.py`, `original_bytes`). Questionnaire text is not redacted: it is the buyer's questions.
- Answers, interview questions, the visitor's own answers (stored as redacted "statements"), suggested fills and an
  audit log of the visitor's actions.
- Retention: a workspace is unusable 24 hours after it was made and deleted, with everything in it, within about
  37 hours by two daily sweeps (05:00 and 17:00 UTC) (`app/services/workspaces.py` WORKSPACE_TTL, `vercel.json`
  crons). "Reset workspace" deletes it at once. Per-network counters are kept 2 days, canary results 30 days.

## What leaves the app
- To OpenRouter, and through it to the model provider it routes to: redacted passages with their file names, the
  question and its topic, and the visitor's redacted answers. Never an uploaded file. Each request asks OpenRouter to
  route only to providers that honour every parameter sent (`app/llm/client.py`).
- To Langfuse (when configured): metadata only (model, prompt version, step, latency, tokens, finish reason, item id),
  never prompts, document text or answers (`app/observability.py`).
- The sample company's documents are synthetic and are not redacted; citations quote the stored line.
- The sample run is precomputed from recorded model replies, so opening it sends nothing to a model provider.

## Redaction
Applied to uploads and to the visitor's own answers before storage and before any model call (`app/redact.py`).
- Found: personal names (Presidio with spaCy's small English model, kept as a name only when it has two or more
  capitalised words and no organisation or product word; once a name is found, its words are redacted elsewhere in
  the same line), email addresses, phone numbers in common formats, US-style street addresses, and secrets (API keys, private keys, tokens,
  JSON web tokens, connection strings with a password, and keyed values such as `password=`).
- Kept on purpose: place names and cloud regions, because data-residency answers need them.
- A file whose redaction would take over 120 seconds is refused (`app/redact.py` DEADLINE_S).
- Known gaps: a "Last, First" name inside a list of names, where a comma or "and" joins the pairs ("Kim, Ortiz,
  Dana"; "Nguyen, Linh and Ortiz, Dana"; a lone "Patel, Priya" is caught); an all-capitals name with accented letters; a single first name
  ("ask Priya"); a name written in lower case. A capitalised word that is also part of a found name is redacted
  even where it is an ordinary word (over-redaction, accepted).

## Content a reader cannot see
Not read as evidence: Word text marked hidden or smaller than 1 point; PDF lines whose first character is smaller
than 1 point; hidden sheets and hidden rows of an uploaded workbook; hidden rows of a questionnaire (never asked or
answered). Known gaps: white or background-coloured text and similar tricks; text hidden by a Word character style;
hidden columns; a tiny phrase inside a readable PDF line; text outside the visible page. PDF text in the "invisible"
render mode is read on purpose: OCR'd scans keep their whole text layer there.

## Prompt injection
Passage text is data, and every system prompt says so. Passages that match the injection patterns are removed
before any model call and shown as dropped (`app/patterns.py`, `app/retrieve.py`). Labels come from code, not from the
model; every quote is re-read from the stored line; the drafted answer may only name cited documents and numbers in
cited quotes. The eval gates CI on zero injections followed, on the dev and holdout packs.

## Limits and cost guards
- Per network, an hour: 20 new workspaces, 60 uploads, 20 runs, 400 model calls, 60 interview answers, 60 exports
  (`app/services/ip_limits.py` LIMITS).
- Per workspace, an hour, per step: stance 150, draft 120, classify 40, recheck 60 model calls; for everyone: 1,500
  model calls an hour and 4,000 a day, counted where a workspace reset cannot refund them
  (`app/services/llm_budget.py`). A step answers its items at the same time (at most 8 model calls in flight), which
  makes a run faster but does not change these counts.
- At most one live run per questionnaire at a time; a run no step has touched for 10 minutes is closed as failed.
- Uploads: PDF, DOCX, XLSX, CSV, MD and TXT, checked by content; at most 4 MB per file, 20 uploaded documents and
  20,000 lines per workspace, 1,000,000 characters per document, 150 questions and 1 MB per questionnaire, 5
  questionnaires; Office files over 50 MB unpacked or 5,000 parts are refused; Word files with tracked changes and
  PDFs with no text layer are refused (`app/ingest/parse.py`, `app/ingest/pdf.py`, `app/questionnaires.py`,
  `app/api/schemas.py`). A storage breaker refuses new work when the database is near its size limit
  (`app/services/capacity.py`).
- The OpenRouter key has its own credit limit; the daily canary reports low credit on /api/health.
- The sample company's run is precomputed, so the default path spends nothing.

## Isolation
A signed, HttpOnly, SameSite=Lax cookie (Secure on Vercel) names the workspace; every query is scoped to it, and
another workspace's ids answer 404. Cross-site writes are refused with 403 before any route runs. Exported cells are
written as inert text, so a formula in an answer never runs in the buyer's spreadsheet (`app/export.py`).

## Secrets
gitleaks finds no secret in the repository or its history: it scans every commit in CI, with an added rule for
bare OpenRouter keys. Production secrets live only in Vercel's environment variables; the eval key lives in a mode-600
file outside the repository with a $5 credit limit.

## Accepted risks of a demo
- A small PDF whose streams inflate past the function's memory can crash its instance; on Fluid compute that ends
  every request in flight there. Parsing in a subprocess with a memory limit would fix it.
- Per-network limits key on the full client address; an IPv6 visitor can rotate within a /64.
- /api/health opens a database connection on every request.
- Vercel deploys main without waiting for CI; releases go through a pull request with green CI first.

## What real use would need
Single sign-on and roles; customer-managed encryption keys; a data processing agreement and zero-retention routing
with every model provider; malware scanning of uploads; OCR for scanned PDFs; a review step for redaction; longer,
customer-controlled retention and audit export; per-tenant isolation; and an independent security assessment.
