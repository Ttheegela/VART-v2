import csv
import io
import uuid
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.schemas import GapRow, Mapping
from app.export import (
    DRAFT,
    FOOTER,
    GAP_HEAD,
    REVIEW,
    ExportRow,
    GapSheet,
    export_csv,
    export_xlsx,
    gap_report,
)
from tests.apiclient import visitor

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "questionnaires"
VSQ = Mapping(
    sheet="Questionnaire",
    header_row=5,
    id_col="A",
    question_col="C",
    answer_col="D",
    comments_col="E",
    topic_col="B",
)
ROWS = [
    ExportRow(
        7,
        "verified",
        "Yes",
        "Yes. The policy says so.",
        True,
        ["information-security-policy.docx line 4"],
        [],
    ),
    ExportRow(
        8, "partial", "Partial", "Partly.", False, ["policy.docx line 2"], ["Scope: internal systems only."]
    ),
    ExportRow(9, "unknown", None, "", False, [], []),
]
PAYLOADS = [
    '=HYPERLINK("https://evil.example","Yes")',
    "@SUM(1+1)",
    "+cmd|' /C calc'!A0",
    "-1+1",
    "\t=1+1",
    "\r=1+1",
    "\n=1+1",
    "=1+1",
]


def test_the_xlsx_keeps_its_formatting_and_gets_three_columns() -> None:
    original = (SAMPLES / "vsq-a.xlsx").read_bytes()
    before = openpyxl.load_workbook(io.BytesIO(original))["Questionnaire"]
    wb = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, ROWS)))
    ws = wb["Questionnaire"]
    assert [ws.cell(5, c).value for c in (6, 7, 8)] == ["Status", "Sources", "Notes"]
    assert (ws["D7"].value, ws["E7"].value, ws["F7"].value) == (
        "Yes",
        "Yes. The policy says so.",
        "Verified · Approved",
    )
    assert ws["G7"].value == "information-security-policy.docx line 4"
    assert ws["F8"].value == f"Partial · {DRAFT}" and ws["F9"].value == f"Unknown · {DRAFT}"
    # Yes/No/N/A validation without "Partial": the value moves to Notes, the answer cell stays empty.
    assert ws["D8"].value is None and "Answer: Partial" in ws["H8"].value
    # Formatting kept, cell by cell where it matters.
    assert {str(r) for r in ws.merged_cells.ranges} == {str(r) for r in before.merged_cells.ranges}
    assert len(ws.data_validations.dataValidation) == len(before.data_validations.dataValidation)
    assert ws.column_dimensions["C"].width == before.column_dimensions["C"].width
    assert ws["C7"].font.b == before["C7"].font.b and ws["A5"].font.b == before["A5"].font.b


def test_the_csv_keeps_its_columns_and_delimiter() -> None:
    original = b"Question;Answer;Comment\r\nIs MFA on?;;\r\nAre logs kept?;;\r\n"
    mapping = Mapping(
        sheet=None, header_row=1, id_col=None, question_col="A", answer_col="B", comments_col="C"
    )
    out = export_csv(original, mapping, [ExportRow(2, "verified", "Yes", "Yes.", False, ["p.md line 1"], [])])
    rows = list(csv.reader(io.StringIO(out.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Question", "Answer", "Comment", "Status", "Sources", "Notes"]
    assert rows[1] == ["Is MFA on?", "Yes", "Yes.", f"Verified · {DRAFT}", "p.md line 1", ""]
    assert rows[2][:3] == ["Are logs kept?", "", ""]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_the_xlsx_cells_are_inert_text(payload: str) -> None:
    # Adversary 1 I1: openpyxl turns a string starting with = into a formula; every cell must stay a string.
    original = (SAMPLES / "vsq-a.xlsx").read_bytes()
    row = ExportRow(7, "verified", "Yes", payload, False, [payload], [payload])
    ws = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, [row])))["Questionnaire"]
    for ref in ("E7", "G7", "H7"):
        assert (ws[ref].data_type, ws[ref].value) == ("s", payload), ref
    # A value that is itself the payload (an answer column without a validation list).
    mapping = Mapping(
        sheet="Questionnaire", header_row=5, id_col="A", question_col="C", answer_col="E", comments_col="D"
    )
    row = ExportRow(7, "unknown", None, payload, False, [], [])
    ws = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, mapping, [row])))["Questionnaire"]
    assert ws["E7"].data_type == "s" and ws["E7"].value == payload


@pytest.mark.parametrize("payload", PAYLOADS)
def test_the_csv_cells_are_inert_text(payload: str) -> None:
    original = b"Question,Answer,Comment\r\nIs MFA on?,,\r\n"
    mapping = Mapping(
        sheet=None, header_row=1, id_col=None, question_col="A", answer_col="B", comments_col="C"
    )
    out = export_csv(original, mapping, [ExportRow(2, "unknown", None, payload, False, [payload], [payload])])
    rows = list(csv.reader(io.StringIO(out.decode("utf-8-sig"), newline="")))
    for cell in rows[1][1:]:
        assert cell.startswith("'") or cell[:1] not in tuple("=+-@\t\r\n"), cell
    assert rows[1][1] == "'" + payload  # the answer cell
    assert rows[1][4] == "'" + payload  # sources


def test_the_endpoint_refuses_an_id_that_is_not_this_workspaces_run(db: Engine) -> None:
    client, _ = visitor(db)
    q = client.post("/api/questionnaires/sample/mvsp-b").json()
    assert client.get(f"/api/runs/{q['id']}/export").status_code == 404  # a questionnaire id is not a run


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("MVSP.csv", 'attachment; filename="MVSP-filled.csv"'),
        ('a"b\r\nSet-Cookie: x=1.xlsx', 'attachment; filename="a_b_Set-Cookie_x_1-filled.xlsx"'),
        ("büro.xlsx", 'attachment; filename="b_ro-filled.xlsx"'),
        ("\r\n.xlsx", 'attachment; filename="questionnaire-filled.xlsx"'),
    ],
)
def test_the_download_header_is_safe(filename: str, expected: str) -> None:
    from urllib.parse import unquote

    from app.api.export import disposition

    head = disposition(filename, filename.rsplit(".", 1)[1])
    assert head.startswith(expected)
    assert not any(c in head for c in "\r\n") and head.isascii()
    if head != expected:
        assert head.count('"') == 2 and unquote(head.split("UTF-8''")[1]).startswith(
            filename.rsplit(".", 1)[0]
        )


def test_a_csv_padding_bomb_is_refused_not_padded() -> None:
    from app.ingest.parse import IngestError

    mapping = Mapping(
        sheet=None, header_row=1, id_col=None, question_col="A", answer_col="B", comments_col=None
    )
    bomb = ("Q,A\r\n" + "\r\n" * 5000 + "," * 20000 + "\r\n").encode()
    with pytest.raises(IngestError):
        export_csv(bomb, mapping, [])
    wide = ("Q,A\r\n" + "," * 60 + "\r\n").encode()
    with pytest.raises(IngestError):
        export_csv(wide, mapping, [])


def test_control_characters_do_not_break_the_xlsx() -> None:
    original = (SAMPLES / "vsq-a.xlsx").read_bytes()
    row = ExportRow(7, "verified", "Yes", "a\x0bb\x0c=1", False, ["s\x01"], [])
    ws = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, [row])))["Questionnaire"]
    assert ws["E7"].value == "ab=1" and ws["G7"].value == "s"


def test_csv_leading_control_characters_are_prefixed() -> None:
    mapping = Mapping(
        sheet=None, header_row=1, id_col=None, question_col="A", answer_col="B", comments_col=None
    )
    out = export_csv(b"Q,A\r\nx,\r\n", mapping, [ExportRow(2, "unknown", None, "\x0b=1", False, [], [])])
    assert list(csv.reader(io.StringIO(out.decode("utf-8-sig"))))[1][1] == "'\x0b=1"


def _run(db: Engine, ws_id: object, *, original: bytes | None, filename: str = "q.csv") -> uuid.UUID:
    from app.db.models import Answer, Item, Questionnaire, Run

    mapping = Mapping(
        sheet=None, header_row=1, id_col=None, question_col="A", answer_col="B", comments_col=None
    )
    with Session(db) as s:
        q = Questionnaire(
            workspace_id=ws_id,
            filename=filename,
            source="upload",
            original_bytes=original,
            mapping={"confirmed": mapping.model_dump()},
        )
        s.add(q)
        s.flush()
        run = Run(workspace_id=ws_id, questionnaire_id=q.id)
        item = Item(workspace_id=ws_id, questionnaire_id=q.id, position=0, row_ref="2", question="Is MFA on?")
        s.add_all([run, item])
        s.flush()
        s.add(
            Answer(
                workspace_id=ws_id, run_id=run.id, item_id=item.id, label="unknown", value=None, text="=1+1"
            )
        )
        s.commit()
        return run.id


def test_the_endpoint_exports_a_real_run_and_isolates_it(db: Engine) -> None:
    client, ws_id = visitor(db)
    run_id = _run(db, ws_id, original=b"Question,Answer\r\nIs MFA on?,\r\n", filename='a"b\r\n.csv')
    r = client.get(f"/api/runs/{run_id}/export")
    assert r.status_code == 200
    head = r.headers["content-disposition"]
    assert head.startswith('attachment; filename="') and "\r" not in head and "\n" not in head
    assert r.text.splitlines()[1].startswith("Is MFA on?,'=1+1,")
    other, _ = visitor(db)
    assert other.get(f"/api/runs/{run_id}/export").status_code == 404
    xl = _run(db, ws_id, original=(SAMPLES / "vsq-a.xlsx").read_bytes(), filename="vsq.xlsx")
    with Session(db) as s:
        from app.db.models import Questionnaire, Run

        qq = s.get_one(Questionnaire, s.get_one(Run, xl).questionnaire_id)
        qq.mapping = {"confirmed": VSQ.model_dump()}
        s.commit()
    rx = client.get(f"/api/runs/{xl}/export")
    assert rx.status_code == 200 and "x-export-notice" in rx.headers
    assert rx.headers["content-disposition"] == 'attachment; filename="vsq-filled.xlsx"'


def test_a_questionnaire_without_its_file_is_a_409(db: Engine) -> None:
    client, ws_id = visitor(db)
    run_id = _run(db, ws_id, original=None)
    assert client.get(f"/api/runs/{run_id}/export").status_code == 409


CONTROLS = "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final"


def _gap_row(
    csf_id: str, tier: Any, label: Any, explanation: str | None, answer_id: Any = None, na: bool = False
) -> GapRow:
    return GapRow(
        csf_id=csf_id,
        function="Protect",
        category="Data Security",
        outcome=f"NIST text of {csf_id}",
        related_controls=["CP-09"],
        source_url="https://csrc.nist.gov/projects/cybersecurity-framework/filters#/csf/filters",
        tier=tier,
        item_id=None,
        answer_id=answer_id,
        label=label,
        explanation=explanation,
        sources=1 if answer_id else 0,
        not_applicable=na,
    )


def test_the_gap_report_lists_every_outcome_in_scope_with_inert_cells() -> None:
    aid = uuid.uuid4()
    cite = {"quote": "=cmd|' /C calc'!A0", "filename": "backup-policy.docx", "line_start": 2}
    rows = [
        _gap_row("PR.DS-11", "checked", "covered", "=SUM(A1)", aid),
        _gap_row("PR.DS-10", "not_checked", None, None),
        _gap_row("PR.DS-01", "checked", None, None),  # not answered yet
        _gap_row("PR.DS-02", "checked", None, "Not applicable: we have no data", na=True),
        _gap_row("GV.RM-02", "ask", None, "Not applicable: not ours", na=True),  # either tier: adversary-1 I1
        _gap_row(
            "PR.DS-03", "checked", None, "Not checked: the model call failed twice. Press r to check again."
        ),
    ]
    body = gap_report(GapSheet(rows, {aid: [cite]}, "2026-10-06", "core", "2.0", CONTROLS))
    ws = openpyxl.load_workbook(io.BytesIO(body))["Gap report"]
    assert ws["A1"].value == REVIEW == "Possible gap — review it"
    assert (ws["B1"].value, ws["C1"].value) == ("Scope: core", "Run date: 2026-10-06")
    assert tuple(c.value for c in ws[2]) == GAP_HEAD
    assert [ws.cell(n, 4).value for n in (3, 4, 5)] == [
        "Covered",
        "Not checked in this version",
        "Not run yet",
    ]
    assert [ws.cell(n, 4).value for n in (6, 7, 8)] == ["Not applicable", "Not applicable", "Failed"]
    assert ws["E8"].value == "Not checked: the model call failed twice."  # the view's UI hint stays out
    assert (ws["E3"].value, ws["E3"].data_type) == ("=SUM(A1)", "s")
    assert (ws["F3"].value, ws["F3"].data_type) == ("\"=cmd|' /C calc'!A0\" (backup-policy.docx line 2)", "s")
    assert (ws["G3"].value, ws["I3"].value, ws["J3"].value, ws["K3"].value) == (
        "NIST text of PR.DS-11",
        "CP-09",
        "2026-10-06",
        "2.0",
    )
    assert ws["H3"].value.endswith(CONTROLS)
    assert ws.cell(10, 1).value == FOOTER == "Not legal advice. CSF 2.0 text © NIST, public domain."


def test_a_questionnaire_xlsx_gains_the_gap_sheet_only_when_given_and_never_overwrites_a_sheet() -> None:
    original = (SAMPLES / "vsq-a.xlsx").read_bytes()
    plain = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, ROWS)))
    assert plain.sheetnames == openpyxl.load_workbook(io.BytesIO(original)).sheetnames  # no gap: unchanged
    gap = GapSheet(
        [_gap_row("RC.RP-01", "checked", "gap", "=1+1", None)], {}, "2026-10-06", "recover", "2.0", CONTROLS
    )
    wb = openpyxl.load_workbook(io.BytesIO(export_xlsx(original, VSQ, ROWS, gap)))
    assert wb.sheetnames == [*plain.sheetnames, "Gap report"]
    assert wb.active.title == plain.active.title  # the visitor's sheet stays the one that opens
    ws = wb["Gap report"]
    assert (ws["B1"].value, ws["A3"].value) == ("Scope: recover", "RC.RP-01")
    assert (ws["E3"].value, ws["E3"].data_type) == ("=1+1", "s")
    taken = openpyxl.load_workbook(io.BytesIO(original))
    taken.create_sheet("Gap report")  # a visitor's own sheet of that name
    buf = io.BytesIO()
    taken.save(buf)
    names = openpyxl.load_workbook(io.BytesIO(export_xlsx(buf.getvalue(), VSQ, ROWS, gap))).sheetnames
    assert names[-2:] == ["Gap report", "Gap report (2)"]
    lower = openpyxl.load_workbook(io.BytesIO(original))
    lower.create_sheet("gap report")  # Excel names are case-insensitive (preflight I4)
    buf = io.BytesIO()
    lower.save(buf)
    names = openpyxl.load_workbook(io.BytesIO(export_xlsx(buf.getvalue(), VSQ, ROWS, gap))).sheetnames
    assert names[-2:] == ["gap report", "Gap report (2)"]


def test_an_ask_me_answer_reads_answered_by_you_and_a_fill_made_covered_reads_confirmed_by_you() -> None:
    """Ruling 14: one label id, two words by tier; an Ask-me "No, not yet" is an answer, not a verdict."""
    rows = [
        _gap_row("GV.RM-02", "ask", "confirmed_by_you", "Your answer: No, not yet.", uuid.uuid4()),
        _gap_row("PR.DS-11", "checked", "confirmed_by_you", "Confirmed by you: part 3.", uuid.uuid4()),
    ]
    body = gap_report(GapSheet(rows, {}, "2026-10-06", "core", "2.0", CONTROLS))
    ws = openpyxl.load_workbook(io.BytesIO(body))["Gap report"]
    assert [ws.cell(n, 4).value for n in (3, 4)] == ["Answered by you", "Confirmed by you"]
