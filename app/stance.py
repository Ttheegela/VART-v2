"""Stance (spec 6.6). Contract stub written by Plan 2A Task 2; Plan 2A Task 6 replaces this file."""

from collections.abc import Sequence
from typing import Literal

from app.contracts import ItemInput, Passage, Stance
from app.llm.client import LLMClient

PROMPT_VERSION = "stance@p1"


def user_prompt(item: ItemInput, passages: Sequence[Passage]) -> str:
    raise NotImplementedError("Plan 2A Task 6")


def stance(
    llm: LLMClient,
    item: ItemInput,
    passages: Sequence[Passage],
    model: str,
    step: Literal["stance", "recheck"] = "stance",
) -> tuple[Stance, ...]:
    raise NotImplementedError("Plan 2A Task 6")
