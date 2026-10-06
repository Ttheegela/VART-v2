"""Export (spec 6.10): write the answers back into the visitor's own file. openpyxl keeps styles, merged
cells, column widths, data validation and conditional formatting; it drops embedded images and charts (a known
openpyxl limit, stated in NOTICE). csv in, csv out. Every cell written is inert text (adversary 1 I1)."""

import csv
import io
import re
import uuid
from copy import copy
from dataclasses import dataclass
from typing import Any

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, MergedCell
from openpyxl.utils import column_index_from_string, get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import csf
from app.api.errors import Conflict
from app.api.schemas import GapRow, Mapping
from app.db.models import Answer, Item
from app.ingest.parse import IngestError, decode
from app.questionnaires import MAX_COLS, MAX_ROWS, delimiter

LABEL_WORDS = {
    "verified": "Verified",
    "partial": "Partial",
    "conflict": "Conflict",
    "unknown": "Unknown",
    "user_confirmed": "Confirmed by you",
    "na": "Not applicable",
}
DRAFT = "Draft, not approved"
APPROVED = "Approved"
ADDED = ("Status", "Sources", "Notes")
NOTICE = "Embedded images and charts are not kept in the exported workbook (an openpyxl limit)."
_ROW = re.compile(r"(\d+)$")
_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n", "\x0b", "\x0c", "\ufeff")
XLSX_MAX_COL = 16384


@dataclass(frozen=True)
class ExportRow:
    row: int
    label: str
    value: str | None
    text: str
    approved: bool
    sources: list[str]
    notes: list[str]


def rows_for(session: Session, run_id: uuid.UUID) -> list[ExportRow]:
    out = []
    pairs = session.execute(
        select(Item, Answer)
        .join(Answer, Answer.item_id == Item.id)
        .where(Answer.run_id == run_id)
        .order_by(Item.position)
    )
    for item, a in pairs:
        m = _ROW.search(item.row_ref)
        if m is None:
            continue
        sources = list(dict.fromkeys(f"{c['filename']} line {c['line_start']}" for c in a.citations))
        notes = [n for n in (a.scope_note,) if n]
        value = "N/A" if a.label == "na" else a.value
        out.append(
            ExportRow(int(m.group(1)), a.label, value, a.text, a.approved_at is not None, sources, notes)
        )
    return out


def _status(r: ExportRow) -> str:
    return f"{LABEL_WORDS[r.label]} · {APPROVED if r.approved else DRAFT}"


def _csv_safe(value: str) -> str:
    return "'" + value if value.startswith(_TRIGGERS) else value


def _put(cell: Any, value: str | None) -> None:
    """Write a string that stays a string: openpyxl would turn a leading = into a formula (data_type 'f')."""
    if value is not None:
        value = ILLEGAL_CHARACTERS_RE.sub("", value)  # openpyxl refuses \x0b, \x0c and friends
    cell.value = value
    if value is not None:
        cell.data_type = "s"


def _cells(
    r: ExportRow, allowed: set[str] | None, has_comments: bool, comments_empty: bool
) -> tuple[str | None, str | None, list[str]]:
    """(answer cell, comments cell, notes) for one row."""
    notes = list(r.notes)
    answer = r.value or (r.text or None)
    if answer is not None and allowed is not None and answer not in allowed:
        # A validation list (Yes/No/N/A) refuses the value or the text: never write it into that cell.
        if r.value:
            notes.insert(0, f"Answer: {r.value}")
        answer = None
    put_text = bool(r.text) and answer != r.text
    to_comments = put_text and has_comments and comments_empty
    if put_text and not to_comments:
        notes.append(f"Answer text: {r.text}")
    return answer, (r.text if to_comments else None), notes


def _validation(ws: Any, letter: str) -> set[str] | None:
    for dv in ws.data_validations.dataValidation:
        if (
            dv.type == "list"
            and dv.formula1
            and dv.formula1.startswith('"')  # a range (=$F$1:$F$3) is not an inline list
            and any(letter == re.sub(r"\d", "", str(c).split(":")[0]) for c in str(dv.sqref).split())
        ):
            return {v.strip() for v in dv.formula1.strip('"').split(",")}
    return None


GAP_SHEET = "Gap report"
GAP_HEAD = (
    "ID",
    "Function",
    "Category",
    "Label",
    "Explanation",
    "Quotes",
    "NIST outcome",
    "Links",
    "Related controls",
    "Run date",
    "CSF version",
)  # CSF spec 7
REVIEW = "Possible gap — review it"
FOOTER = "Not legal advice. CSF 2.0 text © NIST, public domain."
NOT_RUN = "Not run yet"
FAILED_WORD = "Failed"
FAILED_SENTENCE = "Not checked: the model call failed twice."  # the view adds its UI hint


@dataclass(frozen=True)
class GapSheet:
    """One gap-check run as a sheet (CSF spec 7): built by app.api.gap.gap_sheet, written by `_write_gap`."""

    rows: list[GapRow]
    citations: dict[uuid.UUID, list[dict[str, Any]]]
    run_date: str
    scope: str
    version: str
    controls_url: str


def _gap_word(r: GapRow) -> str:
    if r.not_applicable:  # either tier, before the tier test (adversary-1 I1)
        return LABEL_WORDS["na"]
    if r.tier == "not_checked":
        return csf.NOT_CHECKED[0].upper() + csf.NOT_CHECKED[1:]  # "Not checked in this version"
    if r.label:
        return csf.gap_word(r.tier, r.label)
    return FAILED_WORD if _failed(r) else NOT_RUN


def _failed(r: GapRow) -> bool:
    return r.explanation is not None and r.explanation.startswith(FAILED_SENTENCE)


def _write_gap(ws: Any, g: GapSheet) -> None:
    """The review line with the scope and run date, a header, one row per outcome in scope (unchecked ones
    too, so coverage is never overstated), then the not-legal-advice footer. NIST's text is verbatim and
    every cell is inert text (`_put`)."""
    _put(ws.cell(1, 1), REVIEW)
    _put(ws.cell(1, 2), f"Scope: {g.scope}")
    _put(ws.cell(1, 3), f"Run date: {g.run_date}")
    for i, title in enumerate(GAP_HEAD, 1):
        _put(ws.cell(2, i), title)
    for n, r in enumerate(g.rows, 3):
        cited = g.citations.get(r.answer_id, []) if r.answer_id else []
        quotes = "; ".join(
            f'"{c["quote"]}" ({c["filename"]} line {c["line_start"]})'
            + (" (your answer)" if c.get("yours") else "")
            for c in cited
        )
        cells = (
            r.csf_id,
            r.function,
            r.category,
            _gap_word(r),
            FAILED_SENTENCE if _failed(r) else r.explanation,
            quotes or None,
            r.outcome,
            f"{r.source_url} {g.controls_url}",
            ", ".join(r.related_controls) or None,
            g.run_date,
            g.version,
        )
        for i, value in enumerate(cells, 1):
            _put(ws.cell(n, i), value)
    _put(ws.cell(len(g.rows) + 4, 1), FOOTER)
    for i, width in enumerate((10, 10, 28, 20, 60, 60, 60, 40, 20, 12, 10), 1):
        ws.column_dimensions[get_column_letter(i)].width = width


def _free_title(wb: Any, title: str) -> str:
    """A sheet name the visitor's workbook does not use yet: never overwrite their own sheet. Excel's names
    are case-insensitive, so the clash is too (preflight I4)."""
    names, n, name = {x.casefold() for x in wb.sheetnames}, 2, title
    while name.casefold() in names:
        name, n = f"{title} ({n})", n + 1
    return name


def gap_report(g: GapSheet) -> bytes:
    """A gap-check run's own export: a workbook holding only the gap sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = GAP_SHEET
    _write_gap(ws, g)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_xlsx(
    original: bytes, mapping: Mapping, rows: list[ExportRow], gap: GapSheet | None = None
) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(original))
    ws = wb[mapping.sheet] if mapping.sheet else wb.active
    h = mapping.header_row
    a_idx = column_index_from_string(mapping.answer_col)
    c_idx = column_index_from_string(mapping.comments_col) if mapping.comments_col else 0
    first = max(ws.max_column, a_idx, c_idx) + 1  # past every mapped column: a file may have no answer column
    if first + 2 > XLSX_MAX_COL:
        raise Conflict("This sheet has no room for three more columns.")
    style = ws.cell(h, column_index_from_string(mapping.question_col))
    for i, title in enumerate(ADDED):
        cell = ws.cell(h, first + i, title)
        cell.font, cell.fill, cell.border, cell.alignment = (
            copy(style.font),
            copy(style.fill),
            copy(style.border),
            copy(style.alignment),
        )
    allowed = _validation(ws, mapping.answer_col)
    for r in rows:
        comments = f"{mapping.comments_col}{r.row}" if mapping.comments_col else None
        answer, comment, notes = _cells(
            r,
            allowed,
            comments is not None,
            comments is None
            or (ws[comments].value in (None, "") and not isinstance(ws[comments], MergedCell)),
        )
        target = ws[f"{mapping.answer_col}{r.row}"]
        if isinstance(target, MergedCell):  # a merged range cannot be written: the value goes to Notes
            if answer:
                notes.insert(0, f"Answer: {answer}")
        else:
            _put(target, answer)
        if comments and comment:
            _put(ws[comments], comment)
        _put(ws.cell(r.row, first), _status(r))
        _put(ws.cell(r.row, first + 1), "; ".join(r.sources) or None)
        _put(ws.cell(r.row, first + 2), " ".join(notes) or None)
    for i in range(3):
        ws.column_dimensions[get_column_letter(first + i)].width = 28
    if gap is not None:  # plan 6B decision 5: the workspace's latest gap check rides along, after every sheet
        _write_gap(wb.create_sheet(_free_title(wb, GAP_SHEET)), gap)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_csv(original: bytes, mapping: Mapping, rows: list[ExportRow]) -> bytes:
    text = decode(original)
    sep = delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=sep)
    table = [row for _, row in zip(range(MAX_ROWS + 1), reader, strict=False)]
    if len(table) > MAX_ROWS or any(
        len(row) > MAX_COLS for row in table
    ):  # the importer's caps: no padding bomb
        raise IngestError("This file is too large to export into.")
    a = column_index_from_string(mapping.answer_col) - 1
    c = column_index_from_string(mapping.comments_col) - 1 if mapping.comments_col else None
    width = max(max(len(r) for r in table), a + 1, (c + 1) if c is not None else 0)
    table = [r + [""] * (width - len(r)) for r in table]
    table[mapping.header_row - 1] += list(ADDED)
    by_row = {r.row: r for r in rows}
    for n, line in enumerate(table, start=1):
        if n == mapping.header_row:
            continue
        r = by_row.get(n)
        if r is None:
            line += ["", "", ""]
            continue
        answer, comment, notes = _cells(r, None, c is not None, c is None or not line[c])
        line[a] = _csv_safe(answer or "")
        if c is not None and comment:
            line[c] = _csv_safe(comment)
        line += [_csv_safe(s) for s in (_status(r), "; ".join(r.sources), " ".join(notes))]
    out = io.StringIO(newline="")
    csv.writer(out, delimiter=sep, lineterminator="\r\n").writerows(table)
    bom = "\N{ZERO WIDTH NO-BREAK SPACE}" if original.startswith(b"\xef\xbb\xbf") else ""
    return (bom + out.getvalue()).encode("utf-8")
