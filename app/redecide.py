"""Decide again after a metadata override, with no model call (spec 6.7). The passages are rebuilt from the
answer's chunk ids with the documents' current metadata, so a document now marked draft, out of scope or not
evidence changes the label exactly as decide's rules say."""

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app import csf
from app.contracts import DocInfo, Dropped, Passage, Stance, jsonable
from app.db.models import Answer, Chunk, Document, Item, RunItem
from app.decide import decide
from app.draft import template_answer
from app.runs import machine_judged, outcome_values

REDECIDED = ("verified", "partial", "conflict", "unknown")  # plus machine_judged: never the visitor's own


def passages_for(
    session: Session, workspace_id: uuid.UUID, chunk_ids: list[str]
) -> tuple[Passage, ...] | None:
    """The passages in `chunk_ids` order (a stance's `passage` indexes it); None when one chunk is gone."""
    rows = session.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == workspace_id, Chunk.id.in_([uuid.UUID(c) for c in chunk_ids]))
    ).all()
    found = {str(c.id): (c, d) for c, d in rows}
    if len(found) != len(set(chunk_ids)):
        return None
    out = []
    for cid in chunk_ids:
        c, d = found[cid]
        doc = DocInfo(str(d.id), d.filename, d.kind, d.status, d.effective_date, d.scope, d.evidence_allowed)
        out.append(
            Passage(
                cid,
                doc,
                c.line_start,
                tuple(c.text.split("\n")),
                c.heading,
                tuple(c.flags),
                c.as_of,
                c.record,
            )
        )
    return tuple(out)


def _dropped(rows: list[dict[str, Any]]) -> tuple[Dropped, ...]:
    return tuple(Dropped(**r) for r in rows)


def redecide(session: Session, workspace_id: uuid.UUID, document_id: uuid.UUID) -> int:
    """Re-decide every machine-labelled, unedited answer whose passages include a chunk of this document;
    returns how many changed. A changed answer gets the template text and loses its approval."""
    chunk_ids = [str(c) for c in session.scalars(select(Chunk.id).where(Chunk.document_id == document_id))]
    if not chunk_ids:
        return 0
    answers = session.scalars(
        select(Answer)
        .where(
            Answer.workspace_id == workspace_id,
            machine_judged(REDECIDED),
            Answer.edited.is_(False),
            Answer.chunk_ids.has_any(array(chunk_ids)),
        )
        # lock answers first as app/questions.py's lock order says, by id as approve-verified does;
        # a concurrent edit is waited out and then excluded by `edited` (adversary-3 inputs M7)
        .order_by(Answer.id)
        .with_for_update()
    ).all()
    changed = 0
    for a in answers:
        parts = session.scalar(
            select(RunItem.parts).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id)
        )
        if parts:  # a Checked CSF outcome: its row has no stances of its own (CSF spec 5.3)
            changed += _redecide_parts(session, workspace_id, a, parts)
            continue
        passages = passages_for(session, workspace_id, a.chunk_ids)
        if passages is None:
            continue
        stances = tuple(Stance(**s) for s in a.stances)
        d = decide(passages, stances, _dropped(a.retrieval_dropped))
        new = (d.label, d.value, jsonable(d.citations))
        if new == (a.label, a.value, a.citations):
            continue
        a.label, a.value, a.citations = new
        a.dropped = jsonable(d.dropped)
        a.conflict = jsonable(d.conflict)
        a.scope_note = d.scope_note
        a.confidence = d.confidence
        a.text = template_answer(d)
        a.approved_at = None
        changed += 1
    session.commit()
    return changed


def _redecide_parts(session: Session, workspace_id: uuid.UUID, a: Answer, parts: dict[str, Any]) -> int:
    """A CSF outcome after a metadata override: each part decided again from its own stances and passages,
    then combined again (`outcome_values`). A part filled from the visitor's answer keeps its result. 1 when
    the outcome's label, value or citations changed (it then loses its approval), else 0. Writes the run item
    after the answer is locked (app/questions.py's lock order)."""
    o = csf.outcome_or_none(session.get_one(Item, a.item_id).csf_id or "")
    if o is None:
        return 0
    new = dict(parts)
    for k, raw in parts.items():
        if raw.get("statement_id"):
            continue
        passages = passages_for(session, workspace_id, raw["chunk_ids"])
        if passages is None:
            continue
        d = decide(passages, tuple(Stance(**s) for s in raw["stances"]), _dropped(raw["retrieval_dropped"]))
        new[k] = {
            **raw,
            "label": d.label,
            "value": d.value,
            "citations": jsonable(d.citations),
            "dropped": jsonable(d.dropped),
            "conflict": jsonable(d.conflict),
            "scope_note": d.scope_note,
            "confidence": d.confidence,
            "text": template_answer(d),
        }
    if new == parts or len(new) != len(o.parts):
        return 0
    session.execute(
        update(RunItem).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id).values(parts=new)
    )
    values = outcome_values(o, new)
    if (values["label"], values["value"], values["citations"]) == (a.label, a.value, a.citations):
        return 0
    for key, value in values.items():
        setattr(a, key, value)
    a.approved_at = None
    return 1
