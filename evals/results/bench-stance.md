# Model bench: stance (dev pack, 2026-10-05)

Live calls from `python -m evals.bench`, not reproduced in CI; app/settings.py defaults follow it.

| model | items | label_accuracy | conflicts_caught | honest_negatives_kept | failures | cost_usd | p50_seconds |
|---|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash | 89 | 0.8652 | 7 | 6 | 2 | 0.0199 | 6.77 |
| deepseek/deepseek-v4-pro | 89 | 0.9438 | 7 | 6 | 0 | 0.0884 | 12.59 |
| qwen/qwen3.5-flash-02-23 | 89 | 0.0 | 0 | 0 | 89 | - | - |
| qwen/qwen3.7-plus | 89 | 0.8764 | 7 | 6 | 0 | 0.0829 | 8.72 |
| z-ai/glm-5.3-flash | 89 | 0.8876 | 5 | 6 | 0 | 0.0326 | 3.79 |
| moonshotai/kimi-k2.5 | 89 | 0.6966 | 4 | 6 | 12 | 0.137 | 8.48 |
| openai/gpt-oss-120b | 89 | 0.8315 | 6 | 6 | 2 | 0.0184 | 8.02 |
| anthropic/claude-sonnet-5.5 | 89 | 0.9663 | 7 | 5 | 0 | 0.7788 | 3.17 |
