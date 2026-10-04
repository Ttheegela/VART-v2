"""Draft and answer check (spec 6.8). Contract stub written by Plan 2A Task 2; Plan 2A Task 7 replaces this
file."""

from collections.abc import Sequence

from app.contracts import Decision, Draft, ItemInput, Spend
from app.llm.client import LLMClient

PROMPT_VERSION = "draft@p1"


def plain_name(filename: str) -> str:
    raise NotImplementedError("Plan 2A Task 7")


def user_prompt(item: ItemInput, decision: Decision) -> str:
    raise NotImplementedError("Plan 2A Task 7")


def check(text: str, decision: Decision, documents: Sequence[str]) -> list[str]:
    raise NotImplementedError("Plan 2A Task 7")


def template_answer(decision: Decision) -> str:
    raise NotImplementedError("Plan 2A Task 7")


def write_draft(
    llm: LLMClient | None,
    item: ItemInput,
    decision: Decision,
    model: str,
    spend: Spend,
    documents: Sequence[str],
) -> Draft:
    raise NotImplementedError("Plan 2A Task 7")
