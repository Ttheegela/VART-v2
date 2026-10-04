# VART evaluation data

Everything here is public or synthetic. The company in `dev/` is fictional.

- `questionnaires/` — two sample questionnaires a buyer might send: `vsq-a.xlsx` (about 60 questions, deliberately
  messy spreadsheet) and `mvsp-b.csv` (25 questions). `*.selection.yaml` is the source of each.
- `dev/facts.yaml` — the fact sheet: what is true at the company, which document says what, and every planted trap.
- `dev/src/` — document sources; `dev/docs/` — the rendered documents a visitor uploads.
- `dev/key/` — the expected answer for every question, derived from the fact sheet by `datakit/derive_key.py`.
- `mapper/` — ten messy questionnaire files and the column mapping each should get.

Regenerate and check: `python -m datakit.render dev`, `python -m datakit.questionnaires`,
`python -m datakit.derive_key dev`, `python -m datakit.mapper_variants`, then `python -m datakit.validate all`.
