from datetime import date

from app.contracts import Citation, Conflict, ConflictSide, DocInfo, Dropped, Passage, jsonable


def test_a_passage_knows_its_last_line() -> None:
    doc = DocInfo("d", "a.docx", "policy", "final", None, None, True)
    assert Passage("c", doc, 12, ("one", "two", "three"), None, (), None, False).line_end == 14


def test_jsonable_turns_contracts_into_plain_json() -> None:
    cite = Citation("c1", "d1", "log.xlsx", 4, 4, "Status: Overdue", "no")
    conflict = Conflict(
        "date", (ConflictSide("no", (cite,), date(2026, 9, 15)), ConflictSide("yes", (), None))
    )
    out = jsonable({"conflict": conflict, "dropped": [Dropped("c2", "d2", "wiki.md", "injection")]})
    assert out["conflict"]["sides"][0] == {
        "stance": "no",
        "citations": [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "filename": "log.xlsx",
                "line_start": 4,
                "line_end": 4,
                "quote": "Status: Overdue",
                "stance": "no",
                "note": "",
            }
        ],
        "date": "2026-09-15",
    }
    assert out["dropped"] == [
        {"chunk_id": "c2", "document_id": "d2", "filename": "wiki.md", "reason": "injection", "quote": ""}
    ]
