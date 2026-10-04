"""Decide (spec 6.7). Contract stub written by Plan 2A Task 2; Plan 2A Task 4 replaces this file."""

from collections.abc import Sequence

from app.contracts import Decision, Dropped, Passage, Stance


def decide(
    passages: Sequence[Passage], stances: Sequence[Stance], dropped: Sequence[Dropped] = ()
) -> Decision:
    raise NotImplementedError("Plan 2A Task 4")
