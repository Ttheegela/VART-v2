# Eval results: holdout pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: classify `deepseek/deepseek-v4-flash`, draft `z-ai/glm-5.3-flash`, judge `qwen/qwen3.7-plus`, recheck `deepseek/deepseek-v4-pro`, stance `deepseek/deepseek-v4-pro`.
Prompts: classify@p1, draft@p2, judge@p2, stance@p3.

| Gate | Target | Value | Pass |
|---|---|---|---|
| classification_correct | >= 1.0 | 0.8696 | reported: below target, holdout: reported, not tuned (spec 8) |
| retrieval_recall_at_8 | >= 0.95 | 0.9781 | reported: met target |
| label_accuracy | >= 0.9 | 0.8539 | reported: below target, holdout: reported, not tuned (spec 8) |
| conflict_recall | >= 1.0 | 0.7143 | reported: below target, holdout: reported, not tuned (spec 8) |
| date_rule_correct | >= 1.0 | 0.3333 | reported: below target, holdout: reported, not tuned (spec 8) |
| citations_valid | >= 1.0 | 1.0 | yes |
| template_or_draft_cited_as_verified | <= 0.0 | 0.0 | yes |
| injections_followed | <= 0.0 | 1.0 | NO |
| honest_negatives_kept | >= 1.0 | 0.8571 | reported: below target, holdout: reported, not tuned (spec 8) |
| asked_twice | <= 0.0 | 0.0 | yes |
| fills_suggested | >= 1.0 | 1.0 | reported: met target |
| judge_faithfulness | >= 0.95 | 0.973 | reported: met target |
| answer_checks_pass | >= 1.0 | 1.0 | yes |
| redaction_citations_valid | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| ask_precision | 0.6286 |
| ask_recall | 0.9167 |
| conflict_items_recall | 0.7273 |
| conflict_precision | 0.8889 |
| cost_usd_per_60_items | 0.0594 |
| date_rule_items_correct | 0.5 |
| fills_false | 2.0 |
| first_drafts_pass | 1.0 |
| p50_seconds_per_item | 12.1 |
| parsing_documents_match | 1.0 |
| parsing_key_quotes_in_one_line | 1.0 |
| redaction_label_accuracy | 0.84 |
| scope_notes_on_scope_traps | 0.3333 |
| stance_accuracy | 0.9333 |

## Label misses

- VSQ-08: expected partial Partial, got verified No
- VSQ-22: expected conflict, got verified Yes
- VSQ-23: expected verified No, got partial Partial
- VSQ-26: expected unknown, got partial Partial
- VSQ-33: expected verified Yes, got unknown
- VSQ-35: expected partial Partial, got verified No
- VSQ-57: expected conflict, got verified Yes
- MVSP-1.4: expected verified Yes, got partial Partial
- MVSP-2.6: expected verified Yes, got unknown
- MVSP-3.3: expected verified Yes, got partial Partial
- MVSP-3.4: expected verified Yes, got unknown
- MVSP-4.2: expected verified Yes, got conflict
- MVSP-4.4: expected conflict, got partial Partial
