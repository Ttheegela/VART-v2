"""Classify (spec 6.4). Contract stub written by Plan 2A Task 2; Plan 2B Task 3 replaces this file."""

from collections.abc import Sequence

from app.contracts import DocMeta, ParsedDocument, Spend
from app.llm.client import LLMClient

PROMPT_VERSION = "classify@p1"


def rules(fmt: str, texts: Sequence[str]) -> tuple[DocMeta, bool]:
    raise NotImplementedError("Plan 2B Task 3")


def classify(
    filename: str, parsed: ParsedDocument, llm: LLMClient | None, model: str, spend: Spend
) -> DocMeta:
    raise NotImplementedError("Plan 2B Task 3")
