# Eval results: gap-dev pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: draft `z-ai/glm-5.3-flash`, stance `deepseek/deepseek-v4-pro`.
Prompts: draft@p2, stance@p3.

| Gate | Target | Value | Pass |
|---|---|---|---|
| cited_coverage | >= 1.0 | 1.0 | yes |
| trap_coverage | <= 0.0 | 0.0 | yes |
| label_accuracy | >= 0.8 | 0.6774 | NO |
| disagreements_caught | >= 1.0 | 0.5 | NO |
| stated_noncompliance | >= 1.0 | 1.0 | yes |
| nist_text_intact | >= 1.0 | 1.0 | yes |
| honest_tiers | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |
| statements_as_evidence | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| cost_usd_per_core_run | 0.0333 |
| retrieval_recall_at_8 | 0.8393 |
| seconds_per_core_run | 377.97 |

## Label misses

- DE.CM-09: expected covered, got partly_covered
- GV.PO-01: expected covered, got partly_covered
- ID.AM-05: expected partly_covered, got gap
- ID.AM-08: expected partly_covered, got covered
- ID.RA-08: expected covered, got gap
- PR.AA-01: expected covered, got documents_disagree
- PR.AA-05: expected documents_disagree, got partly_covered
- PR.PS-01: expected covered, got partly_covered
- RC.RP-01: expected covered, got gap
- RS.CO-02: expected partly_covered, got covered
