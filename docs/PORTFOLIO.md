# Portfolio entry: VART v2

**VART v2: security questionnaires answered from a company's own documents, with citations.**
Solo rebuild (2026) of a 4-person hackathon project (Money Talks AI x Finance Hackathon, NYC, 2026-09-05).

- Fills a vendor security questionnaire from a company's policies, audit reports and spreadsheets; every answer
  cites the exact line it came from, contradictions between documents are flagged, and the person is asked only
  what the documents do not cover. Exports back into the buyer's own spreadsheet. Also checks documents against
  NIST CSF 2.0.
- Labels are decided by code, not by the model; quotes are re-read from the source before they show.
- Evals in CI on a dev company and a holdout company built after the engine was frozen: label accuracy 0.9326 dev
  and 0.8539 holdout, conflict recall 1.0 dev and 0.7143 holdout, citations valid 1.0 and 1.0, injections followed
  0.0 and 0.0 (the holdout is reported, not tuned; one metric's definition changed after its first score and is
  disclosed in `docs/EVALS.md`).
- Production: FastAPI on Vercel, Neon Postgres, OpenRouter (open-weight models chosen by a bench), React +
  TypeScript, record/replay model calls, per-network and global budgets, PII and secret redaction, Langfuse
  tracing, health checks, a daily canary, UptimeRobot; a 64-item run in about 4 minutes (231 s), the sample company
  instant and free.
- Live: https://vart-v2.vercel.app · Code: https://github.com/Ttheegela/VART-v2
