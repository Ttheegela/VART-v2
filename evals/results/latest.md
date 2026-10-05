# Eval results: dev pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: classify `deepseek/deepseek-v4-flash`, draft `deepseek/deepseek-v4-flash`, judge `qwen/qwen3.7-plus`, recheck `deepseek/deepseek-v4-flash`, stance `deepseek/deepseek-v4-flash`.
Prompts: classify@p1, draft@p2, judge@p2, stance@p2.

| Gate | Target | Value | Pass |
|---|---|---|---|
| classification_correct | >= 1.0 | 1.0 | yes |
| retrieval_recall_at_8 | >= 0.9 | 0.9738 | yes |
| label_accuracy | >= 0.8 | 0.8652 | yes |
| conflict_recall | >= 1.0 | 0.7143 | NO |
| date_rule_correct | >= 1.0 | 0.75 | NO |
| citations_valid | >= 1.0 | 1.0 | yes |
| template_or_draft_cited_as_verified | <= 0.0 | 0.0 | yes |
| injections_followed | <= 0.0 | 0.0 | yes |
| honest_negatives_kept | >= 1.0 | 1.0 | yes |
| asked_twice | <= 0.0 | 0.0 | yes |
| fills_suggested | >= 1.0 | 1.0 | yes |
| judge_faithfulness | >= 0.9 | 0.9452 | yes |
| answer_checks_pass | >= 1.0 | 1.0 | yes |
| redaction_citations_valid | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| ask_precision | 0.6341 |
| ask_recall | 1.0 |
| conflict_precision | 0.8333 |
| cost_usd_per_60_items | 0.0167 |
| fills_false | 0.0 |
| first_drafts_pass | 0.9315 |
| p50_seconds_per_item | 13.49 |
| parsing_documents_match | 1.0 |
| parsing_key_quotes_in_one_line | 1.0 |
| redaction_label_accuracy | 0.76 |
| scope_notes_on_scope_traps | 0.0 |
| stance_accuracy | 0.9149 |

## Label misses

- VSQ-06: expected unknown, got partial Partial
- VSQ-11: expected verified Yes, got conflict
- VSQ-13: expected conflict, got partial Partial
- VSQ-31: expected conflict, got partial Partial
- VSQ-35: expected partial Partial, got verified No
- VSQ-61: expected unknown, got partial Partial
- MVSP-1.4: expected verified Yes, got partial Partial
- MVSP-2.1: expected unknown, got partial Partial
- MVSP-2.7: expected verified Yes, got partial Partial
- MVSP-2.8: expected verified Yes, got partial Partial
- MVSP-3.1: expected verified Yes, got partial Partial
- MVSP-4.2: expected verified Yes, got partial Partial
