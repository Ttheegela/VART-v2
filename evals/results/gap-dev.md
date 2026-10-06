# Eval results: gap-dev pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: draft `z-ai/glm-5.3-flash`, stance `deepseek/deepseek-v4-pro`.
Prompts: draft@p2, stance@p3.

| Gate | Target | Value | Pass |
|---|---|---|---|
| cited_coverage | >= 1.0 | 1.0 | yes |
| trap_coverage | <= 0.0 | 1.0 | NO |
| label_accuracy | >= 0.8 | 0.6129 | NO |
| disagreements_caught | >= 1.0 | 1.0 | yes |
| stated_noncompliance | >= 1.0 | 1.0 | yes |
| nist_text_intact | >= 1.0 | 1.0 | yes |
| honest_tiers | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |
| statements_as_evidence | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| cost_usd_per_core_run | 0.0358 |
| part_agreement | 0.6667 |
| retrieval_recall_at_8 | 0.6786 |
| seconds_per_core_run | 793.25 |

## Label misses

- DE.CM-09: expected covered, got partly_covered
- GV.PO-01: expected covered, got gap
- ID.RA-01: expected covered, got partly_covered
- ID.RA-08: expected covered, got partly_covered
- PR.AA-06: expected gap, got partly_covered
- PR.DS-01: expected covered, got partly_covered
- PR.IR-03: expected partly_covered, got covered
- PR.PS-01: expected covered, got gap
- PR.PS-02: expected partly_covered, got gap
- RC.RP-01: expected covered, got gap
- RS.CO-02: expected partly_covered, got documents_disagree
- RS.MA-01: expected partly_covered, got gap
