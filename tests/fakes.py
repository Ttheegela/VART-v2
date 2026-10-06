import threading

from app.llm.client import LLMRequest, LLMResult


class FakeLLM:
    """Scripted replies, used in order. An Exception item is raised instead. Every request is kept."""

    def __init__(self, replies: list[str | Exception] | None = None) -> None:
        self.replies = list(replies or [])
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResult:
        self.requests.append(req)
        if not self.replies:
            raise AssertionError(f"FakeLLM ran out of replies at step {req.step}")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, input_tokens=10, output_tokens=5, cost_usd=0.0)


class ByStepLLM:
    """Answers by step, safe across threads (the runner's concurrency tests). Counts requests per step."""

    def __init__(self, replies: dict[str, str | Exception], cost: float = 0.0) -> None:
        self.replies = replies
        self.cost = cost
        self.requests: list[LLMRequest] = []
        self._lock = threading.Lock()

    def complete(self, req: LLMRequest) -> LLMResult:
        with self._lock:
            self.requests.append(req)
        reply = self.replies[req.step]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, input_tokens=10, output_tokens=5, cost_usd=self.cost)
