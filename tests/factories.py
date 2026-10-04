"""Tiny row builders for tests. Each one flushes so ids are set; callers commit when they need to."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Answer, Chunk, Document, Item, Questionnaire, Run, Workspace

CITATION: dict[str, Any] = {
    "chunk_id": "c1",
    "document_id": "d1",
    "line_start": 1,
    "line_end": 1,
    "quote": "Access is reviewed quarterly.",
    "stance": "yes",
}


def workspace(s: Session, **kw: Any) -> Workspace:
    ws = Workspace(**kw)
    s.add(ws)
    s.flush()
    return ws


def document(s: Session, ws: Workspace, **kw: Any) -> Document:
    values: dict[str, Any] = {
        "filename": "policy.docx",
        "source": "upload",
        "sha256": uuid.uuid4().hex * 2,
        "kind": "policy",
    }
    d = Document(workspace_id=ws.id, **(values | kw))
    s.add(d)
    s.flush()
    return d


def chunk(s: Session, doc: Document, **kw: Any) -> Chunk:
    values: dict[str, Any] = {"line_start": 1, "line_end": 1, "text": "Access is reviewed quarterly."}
    c = Chunk(workspace_id=doc.workspace_id, document_id=doc.id, **(values | kw))
    s.add(c)
    s.flush()
    return c


def questionnaire(s: Session, ws: Workspace, **kw: Any) -> Questionnaire:
    q = Questionnaire(workspace_id=ws.id, **({"filename": "q.xlsx", "source": "upload"} | kw))
    s.add(q)
    s.flush()
    return q


def item(s: Session, q: Questionnaire, **kw: Any) -> Item:
    values: dict[str, Any] = {
        "position": 1,
        "row_ref": "Questionnaire!C6",
        "question": "Do you review access?",
    }
    it = Item(workspace_id=q.workspace_id, questionnaire_id=q.id, **(values | kw))
    s.add(it)
    s.flush()
    return it


def run(s: Session, q: Questionnaire, **kw: Any) -> Run:
    r = Run(workspace_id=q.workspace_id, questionnaire_id=q.id, **kw)
    s.add(r)
    s.flush()
    return r


def answer(s: Session, r: Run, it: Item, **kw: Any) -> Answer:
    a = Answer(workspace_id=r.workspace_id, run_id=r.id, item_id=it.id, **({"label": "unknown"} | kw))
    s.add(a)
    s.flush()
    return a
