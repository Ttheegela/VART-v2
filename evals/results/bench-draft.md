# Model bench: draft (dev pack, 2026-10-05)

Live calls from `python -m evals.bench`, not reproduced in CI; app/settings.py defaults follow it.

| model | items | first_drafts_pass | fallbacks | judge_faithfulness | failures | cost_usd | p50_seconds | judge |
|---|---|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash | 72 | 0.9167 | 4 | 0.8889 | 4 | 0.0174 | 1.74 | qwen/qwen3.7-plus |
| deepseek/deepseek-v4-pro | 72 | 0.8194 | 9 | 0.8056 | 9 | 0.1126 | 3.83 | qwen/qwen3.7-plus |
| qwen/qwen3.5-flash-02-23 | 72 | 0.0 | 72 | 0.0 | 72 | - | - | moonshotai/kimi-k2.5 |
| qwen/qwen3.7-plus | 72 | 0.0417 | 69 | 0.0417 | 69 | 0.0063 | 13.72 | moonshotai/kimi-k2.5 |
| z-ai/glm-5.3-flash | 72 | 0.9722 | 2 | 0.9306 | 2 | 0.0284 | 1.83 | qwen/qwen3.7-plus |
| moonshotai/kimi-k2.5 | 72 | 0.6528 | 25 | 0.625 | 25 | 0.5242 | 14.06 | qwen/qwen3.7-plus |
| openai/gpt-oss-120b | 72 | 0.9861 | 1 | 0.875 | 1 | 0.0139 | 1.58 | qwen/qwen3.7-plus |
| anthropic/claude-sonnet-5.5 | 72 | 0.9583 | 0 | 0.8611 | 2 | 0.2041 | 1.57 | qwen/qwen3.7-plus |
| anthropic/claude-sonnet-5.5 | 72 | 0.9583 | 0 | 0.9306 | 2 | 0.2041 | 1.57 | moonshotai/kimi-k2.5 |
