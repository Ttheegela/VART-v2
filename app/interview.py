"""Interview (spec 6.9): who to ask first, when to ask once more, and which open items a visitor's answer can
fill. plan_queue and follow_up are pure; recheck makes one budgeted stance call per open item in the answered
item's topic and only ever suggests (spec: never applied silently)."""

import re
import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy.orm import Session

from app.contracts import Dropped, OpenItem, OpenLabel, QueueEntry, Spend, Suggestion
from app.decide import decide
from app.llm.client import LLMClient, LLMError
from app.llm.recorder import ReplayMiss
from app.retrieve import document_passages
from app.stance import stance

OPEN = ("conflict", "unknown", "partial")
# Spec 5 step 6: access control, data security, vulnerability management, incident response and
# business continuity, matched by keyword in free-form section names: an approximation that only orders
# the queue.
HIGH_WEIGHT = re.compile(
    r"\b(?:access|data|vulnerab\w*|incident|continuity|disaster|backup|recovery|encrypt\w*)", re.IGNORECASE
)
_ASKS_FREQUENCY = re.compile(
    r"\bhow often\b|\bfrequen\w*|\b(?:daily|weekly|monthly|quarterly|annual\w*|yearly)\b", re.IGNORECASE
)
_ASKS_NUMBER = re.compile(r"\bhow (?:many|much|long)\b|\bat least\b|\bwithin\b|\blimit\b|%|\d", re.IGNORECASE)
_ASKS_NAME = re.compile(r"\bwho\b|\bnames?\b|\bcontact\b", re.IGNORECASE)
_HAS_FREQUENCY = re.compile(
    r"\b(?:hourly|daily|weekly|monthly|quarterly|annual\w*|yearly|every|once|twice)\b"
    r"|\bper (?:day|week|month|quarter|year)\b",
    re.IGNORECASE,
)
_HAS_NUMBER = re.compile(r"\d")
_HAS_NAME = re.compile(r"<PERSON>|<EMAIL>|\S+@\S+|\b[A-Z][a-z]+ [A-Z][a-z]+\b")


def high_weight(topic: str | None) -> bool:
    return bool(topic and HIGH_WEIGHT.search(topic))


def plan_queue(items: Sequence[OpenItem]) -> list[QueueEntry]:
    """Conflicts first, then unknown and partial items in high-weight topics, then the rest, in questionnaire
    order inside each group. An item already asked is never queued again; its one follow-up is follow_up's."""
    todo = [o for o in items if o.label in OPEN and o.asked == 0]

    def group(i: int) -> tuple[int, int]:
        o = todo[i]
        return (0 if o.label == "conflict" else 1 if high_weight(o.item.topic) else 2), i

    return [
        QueueEntry(
            todo[i].item.key,
            cast(OpenLabel, todo[i].label),
            todo[i].prompt or todo[i].item.question,
            high_weight(todo[i].item.topic),
        )
        for i in sorted(range(len(todo)), key=group)
    ]


def follow_up(question: str, answer: str) -> str | None:
    """The one follow-up when the answer lacks the frequency, number or name the question asks for (v1's
    ladder); None when it has them. The caller asks it only after the first answer (asked == 1)."""
    missing: list[str] = []
    if _ASKS_FREQUENCY.search(question):  # "at least quarterly" asks how often, not for a number
        if not _HAS_FREQUENCY.search(answer):
            missing.append("how often")
    elif _ASKS_NUMBER.search(question) and not _HAS_NUMBER.search(answer):
        missing.append("the number")
    if _ASKS_NAME.search(question) and not _HAS_NAME.search(answer):
        missing.append("the name of the person or team")
    if not missing:
        return None
    return f'To answer "{question}" the buyer also needs {" and ".join(missing)}. Could you add it?'


def recheck(
    session: Session,
    workspace_id: uuid.UUID,
    statement_id: uuid.UUID,
    topic: str | None,
    items: Sequence[OpenItem],
    llm: LLMClient,
    model: str,
    spend: Spend,
) -> list[Suggestion]:
    """Re-check open items in `topic` against the visitor's new statement document: one stance call each
    (step "recheck"), decided by the same rules. Suggests only verified or partial results. A chunk flagged
    `injection` never reaches the model and is recorded as dropped (spec 6.5 and 9)."""
    every = document_passages(session, workspace_id, statement_id)
    passages = tuple(p for p in every if "injection" not in p.flags)
    dropped = tuple(
        Dropped(p.chunk_id, p.doc.id, p.doc.filename, "injection") for p in every if "injection" in p.flags
    )
    session.commit()  # no transaction stays open across the model calls
    found: list[Suggestion] = []
    for o in items:
        if o.label not in OPEN or o.item.topic != topic or not passages:
            continue
        if not spend("recheck"):
            break  # the rest stay open; nothing was applied, so nothing is lost
        try:
            stances = stance(llm, o.item, passages, model, step="recheck")
        except ReplayMiss:
            raise
        except LLMError:
            continue  # this item stays open
        decision = decide(passages, stances, dropped)
        if decision.label in ("verified", "partial"):
            found.append(Suggestion(o.item.key, decision))
    return found
