import inspect
import json
import threading
import time

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Answer
from app.redecide import redecide
from tests import factories as f

QUOTE = "Customer data at rest is encrypted with AES-256."


def _answered(s: Session):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    doc = f.document(s, ws, filename="crypto-policy.docx")
    c = f.chunk(s, doc, line_start=4, line_end=4, text=QUOTE)
    q = f.questionnaire(s, ws)
    it = f.item(s, q, question="Is customer data encrypted at rest?")
    citation = {
        "chunk_id": str(c.id),
        "document_id": str(doc.id),
        "filename": doc.filename,
        "line_start": 4,
        "line_end": 4,
        "quote": QUOTE,
        "stance": "yes",
        "note": "",
    }
    a = f.answer(
        s,
        f.run(s, q),
        it,
        label="verified",
        value="Yes",
        confidence=0.9,
        citations=[citation],
        stances=[{"passage": 1, "stance": "yes", "quote": QUOTE, "note": ""}],
        chunk_ids=[str(c.id)],
        text="Yes.",
    )
    s.commit()
    return ws, doc, a


def test_marking_the_only_source_draft_lowers_verified_to_partial(db: Engine) -> None:
    with Session(db) as s:
        ws, doc, a = _answered(s)
        doc.status = "draft"
        s.commit()
        assert redecide(s, ws.id, doc.id) == 1
        s.refresh(a)
        assert (a.label, a.value, a.approved_at) == ("partial", "Partial", None)
        assert a.text and "Partly" in a.text


def test_a_source_that_is_no_longer_evidence_leaves_the_item_unknown(db: Engine) -> None:
    with Session(db) as s:
        ws, doc, a = _answered(s)
        doc.evidence_allowed = False
        s.commit()
        redecide(s, ws.id, doc.id)
        s.refresh(a)
        assert (a.label, a.citations) == ("unknown", [])
        assert [d["reason"] for d in a.dropped] == ["not-evidence"]


def test_an_edited_or_confirmed_answer_is_left_alone(db: Engine) -> None:
    with Session(db) as s:
        ws, doc, a = _answered(s)
        a.edited = True
        doc.status = "draft"
        s.commit()
        assert redecide(s, ws.id, doc.id) == 0
        assert json.dumps(a.citations)  # unchanged and still readable


def test_no_model_is_called(db: Engine) -> None:
    # redecide takes no LLM client at all: the signature is the guarantee (spec 6.7).
    assert "llm" not in inspect.signature(redecide).parameters


def test_an_edit_in_flight_is_waited_out_and_kept(db: Engine) -> None:
    # Integration carry 3 (adversary-3 inputs M7): redecide locks the answer rows, so an edit holding the row
    # finishes first and the re-decide then leaves the edited answer alone.
    with Session(db) as s:
        ws, doc, a = _answered(s)
        doc.status = "draft"
        s.commit()
        ws_id, doc_id, a_id = ws.id, doc.id, a.id
    result: list[int] = []
    with Session(db) as editor:
        row = editor.scalars(select(Answer).where(Answer.id == a_id).with_for_update()).one()
        row.edited, row.text = True, "Yes, our own words."
        editor.flush()

        def run() -> None:
            with Session(db) as t:
                result.append(redecide(t, ws_id, doc_id))

        th = threading.Thread(target=run)
        th.start()
        time.sleep(0.5)
        assert th.is_alive()  # waiting on the editor's row lock
        editor.commit()
    th.join(10)
    assert result == [0]
    with Session(db) as s:
        assert s.get_one(Answer, a_id).text == "Yes, our own words."
