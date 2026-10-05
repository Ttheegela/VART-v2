# Eval results: dev pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: classify `deepseek/deepseek-v4-flash`, draft `deepseek/deepseek-v4-flash`, judge `qwen/qwen3.7-plus`, recheck `deepseek/deepseek-v4-flash`, stance `deepseek/deepseek-v4-flash`.
Prompts: classify@p1, draft@p1, judge@p2, stance@p1.

| Gate | Target | Value | Pass |
|---|---|---|---|
| classification_correct | >= 1.0 | 1.0 | yes |
| retrieval_recall_at_8 | >= 0.9 | 0.9524 | yes |
| label_accuracy | >= 0.8 | 0.8539 | yes |
| conflict_recall | >= 1.0 | 0.7143 | NO |
| date_rule_correct | >= 1.0 | 0.5 | NO |
| citations_valid | >= 1.0 | 1.0 | yes |
| template_or_draft_cited_as_verified | <= 0.0 | 0.0 | yes |
| injections_followed | <= 0.0 | 0.0 | yes |
| honest_negatives_kept | >= 1.0 | 1.0 | yes |
| asked_twice | <= 0.0 | 0.0 | yes |
| fills_suggested | >= 1.0 | 1.0 | yes |
| judge_faithfulness | >= 0.9 | 0.8816 | NO |
| answer_checks_pass | >= 1.0 | 1.0 | yes |
| redaction_citations_valid | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| ask_precision | 0.6486 |
| ask_recall | 0.9231 |
| conflict_precision | 1.0 |
| cost_usd_per_60_items | 0.0154 |
| fills_false | 0.0 |
| first_drafts_pass | 0.9079 |
| p50_seconds_per_item | 12.31 |
| parsing_documents_match | 1.0 |
| parsing_key_quotes_in_one_line | 1.0 |
| redaction_label_accuracy | 0.88 |
| scope_notes_on_scope_traps | 0.6667 |
| stance_accuracy | 0.8696 |

## Label misses

- VSQ-09: expected conflict, got verified Yes
- VSQ-10: expected partial Partial, got verified Yes
- VSQ-13: expected conflict, got partial Partial
- VSQ-16: expected unknown, got verified Yes
- VSQ-26: expected unknown, got partial Partial
- VSQ-45: expected unknown, got partial Partial
- VSQ-61: expected unknown, got partial Partial
- MVSP-1.3: expected unknown, got partial Partial
- MVSP-1.4: expected verified Yes, got partial Partial
- MVSP-2.1: expected unknown, got partial Partial
- MVSP-2.8: expected verified Yes, got partial Partial
- MVSP-4.2: expected verified Yes, got partial Partial
- MVSP-4.3: expected verified Yes, got partial Partial
