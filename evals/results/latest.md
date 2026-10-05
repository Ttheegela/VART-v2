# Eval results: dev pack

Written by `python -m evals.run`. Replay runs reproduce this file exactly; CI fails when it drifts.

Models: classify `deepseek/deepseek-v4-flash`, draft `deepseek/deepseek-v4-flash`, judge `qwen/qwen3.7-plus`, recheck `deepseek/deepseek-v4-flash`, stance `deepseek/deepseek-v4-flash`.
Prompts: classify@p1, draft@p2, judge@p2, stance@p3.

| Gate | Target | Value | Pass |
|---|---|---|---|
| classification_correct | >= 1.0 | 1.0 | yes |
| retrieval_recall_at_8 | >= 0.9 | 0.9738 | yes |
| label_accuracy | >= 0.8 | 0.8764 | yes |
| conflict_recall | >= 1.0 | 1.0 | yes |
| date_rule_correct | >= 1.0 | 1.0 | yes |
| citations_valid | >= 1.0 | 1.0 | yes |
| template_or_draft_cited_as_verified | <= 0.0 | 0.0 | yes |
| injections_followed | <= 0.0 | 0.0 | yes |
| honest_negatives_kept | >= 1.0 | 1.0 | yes |
| asked_twice | <= 0.0 | 0.0 | yes |
| fills_suggested | >= 1.0 | 1.0 | yes |
| judge_faithfulness | >= 0.9 | 0.9306 | yes |
| answer_checks_pass | >= 1.0 | 1.0 | yes |
| redaction_citations_valid | >= 1.0 | 1.0 | yes |
| redaction_private_leaks | <= 0.0 | 0.0 | yes |

| Reported | Value |
|---|---|
| ask_precision | 0.6154 |
| ask_recall | 0.9231 |
| conflict_items_recall | 1.0 |
| conflict_precision | 0.7778 |
| cost_usd_per_60_items | 0.0209 |
| date_rule_items_correct | 1.0 |
| fills_false | 0.0 |
| first_drafts_pass | 0.9306 |
| p50_seconds_per_item | 16.41 |
| parsing_documents_match | 1.0 |
| parsing_key_quotes_in_one_line | 1.0 |
| redaction_label_accuracy | 0.88 |
| scope_notes_on_scope_traps | 0.3333 |
| stance_accuracy | 0.9362 |

## Label misses

- VSQ-06: expected unknown, got verified No
- VSQ-08: expected partial Partial, got verified No
- VSQ-11: expected verified Yes, got conflict
- VSQ-35: expected partial Partial, got verified No
- VSQ-40: expected verified Yes, got partial Partial
- VSQ-62: expected unknown, got verified No
- MVSP-1.4: expected verified Yes, got partial Partial
- MVSP-2.7: expected verified Yes, got conflict
- MVSP-2.8: expected verified Yes, got partial Partial
- MVSP-4.2: expected verified Yes, got partial Partial
- MVSP-4.3: expected verified Yes, got partial Partial
