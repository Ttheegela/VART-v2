import csv
import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from openpyxl.utils import column_index_from_string

from datakit import mapper_variants, validate
from datakit.mapper_variants import VARIANTS, build_all
from datakit.questionnaires import OUT as QDIR
from datakit.schemas import Selection, SelectionItem, load_yaml
from datakit.validate import DATA, STAGES


def test_ten_variants_with_mappings_that_point_at_real_headers(tmp_path: Path) -> None:
    expected = build_all(tmp_path)
    assert len(expected) == 10
    for name, m in expected.items():
        path = tmp_path / name
        if name.endswith(".xlsx"):
            ws = openpyxl.load_workbook(str(path))[m["sheet"]]
            question_header = ws[f"{m['question_col']}{m['header_row']}"].value
        else:
            delimiter = ";" if name == "v07.csv" else ","
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f, delimiter=delimiter))
            question_header = rows[int(m["header_row"]) - 1][int(m["question_col"]) - 1]
        assert question_header in {"Question", "Questions", "Control Question", "Pregunta"}, name


def test_build_is_deterministic(tmp_path: Path) -> None:
    build_all(tmp_path / "a")
    build_all(tmp_path / "b")
    for p in sorted((tmp_path / "a").iterdir()):
        assert p.read_bytes() == (tmp_path / "b" / p.name).read_bytes(), p.name


NAMES = [f"v{n:02d}.{'csv' if n in (7, 8) else 'xlsx'}" for n in range(1, 11)]
MAPPING_KEYS = ["answer_col", "comments_col", "header_row", "id_col", "question_col", "sheet"]


Built = tuple[Path, dict[str, dict[str, Any]]]  # the folder the ten files were built into, their mappings


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    out = tmp_path_factory.mktemp("mapper")
    return out, build_all(out)


def _grid(path: Path, sheet: str | None) -> list[list[Any]]:
    """Every row of the sheet (or CSV file) as written; None where a cell is empty or merged away."""
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.reader(f, delimiter=";" if path.name == "v07.csv" else ","))
    return [list(row) for row in openpyxl.load_workbook(str(path))[sheet].iter_rows(values_only=True)]


def _index(col: str) -> int:
    """0-based position of a mapped column: a letter in a workbook, a 1-based number string in a CSV file."""
    return int(col) - 1 if col.isdigit() else column_index_from_string(col) - 1


def _sheet(built: Built, name: str) -> Any:
    out, expected = built
    return openpyxl.load_workbook(str(out / name))[expected[name]["sheet"]]


def _first_20() -> tuple[SelectionItem, ...]:
    return load_yaml(QDIR / "vsq-a.selection.yaml", Selection).items[:20]


def test_the_files_and_expected_json_are_what_the_interface_says(built: Built) -> None:
    out, expected = built
    assert [v.__name__ for v in VARIANTS] == [n.split(".")[0] for n in NAMES]
    assert list(expected) == NAMES
    assert sorted(p.name for p in out.iterdir()) == sorted([*NAMES, "expected.json"])
    text = (out / "expected.json").read_text(encoding="utf-8")
    assert text == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    for name, m in expected.items():
        assert sorted(m) == MAPPING_KEYS, name
        if name.endswith(".xlsx"):  # a sheet name, a row number, column letters
            assert m["sheet"] in openpyxl.load_workbook(str(out / name)).sheetnames, name
            assert isinstance(m["header_row"], int) and m["header_row"] >= 1, name
            cols = [m[k] for k in MAPPING_KEYS if k.endswith("_col") and m[k] is not None]
            assert all(re.fullmatch(r"[A-Z]", c) for c in cols), name
        else:  # no sheet, row "1", 1-based column numbers as strings
            assert m["sheet"] is None and m["header_row"] == "1", name
            cols = [m[k] for k in MAPPING_KEYS if k.endswith("_col") and m[k] is not None]
            assert all(c.isdigit() and int(c) >= 1 for c in cols), name


# The header row(s) of every variant exactly as written (None: an empty cell or one merged away).
HEADER_ROWS: dict[str, list[list[str | None]]] = {
    "v01.xlsx": [["Question", "Answer", "Comments"]],
    "v02.xlsx": [["ID", "Question", "Response", "Notes"]],
    "v03.xlsx": [["Ref", "Questions", "Answer", "Comments"]],
    "v04.xlsx": [["Question", "Response", None], [None, "Yes/No", "Details"]],
    "v05.xlsx": [["#", "Control Question", "Response", "Notes"]],
    "v06.xlsx": [["Question", "Answer", "Comments"]],
    "v07.csv": [["Question", "Answer", "Comment"]],
    "v08.csv": [["Question ID", "Question", "Answer", "Comments"]],
    "v09.xlsx": [["Pregunta", "Respuesta", "Comentarios"]],
    "v10.xlsx": [["Weight", "Control ID", "Question", "Answer", "Comments", "Owner"]],
}
# Which header texts each mapped column may carry. "Question ID" is an ID, not the question.
ROLES = {
    "id_col": {"ID", "Ref", "#", "Question ID", "Control ID"},
    "question_col": {"Question", "Questions", "Control Question", "Pregunta"},
    "answer_col": {"Answer", "Response", "Yes/No", "Respuesta"},
    "comments_col": {"Comments", "Notes", "Details", "Comment", "Comentarios"},
}
EXTRA_COLUMNS = {"v10.xlsx": {"Weight", "Owner"}}  # columns that no mapping role claims


def test_each_mapping_points_at_the_header_columns_of_its_file(built: Built) -> None:
    out, expected = built
    assert list(HEADER_ROWS) == NAMES
    for name, rows in HEADER_ROWS.items():
        m = expected[name]
        top = int(m["header_row"]) - 1
        assert _grid(out / name, m["sheet"])[top : top + len(rows)] == rows, name
        claimed = {_index(m[role]) for role in ROLES if m[role] is not None}
        assert len(claimed) == sum(m[role] is not None for role in ROLES), name  # no column claimed twice
        for role, accepted in ROLES.items():
            if m[role] is None:  # no ID column: the header has no ID-like text at all
                assert not accepted & {c for row in rows for c in row}, (name, role)
            else:
                assert accepted & {row[_index(m[role])] for row in rows}, (name, role)
        unclaimed = {row[i] for row in rows for i in range(len(row)) if i not in claimed} - {None}
        assert unclaimed == EXTRA_COLUMNS.get(name, set()), name


def test_every_variant_carries_the_first_20_questions_in_the_mapped_column(
    built: Built,
) -> None:
    out, expected = built
    items = _first_20()
    assert [i.code for i in items] == [f"VSQ-{n:02d}" for n in range(1, 21)]
    for name, m in expected.items():
        below = _grid(out / name, m["sheet"])[int(m["header_row"]) :]  # under the (last) header row
        cells = [row[_index(m["question_col"])] for row in below]
        assert [" ".join(c.split()) for c in cells if c] == [i.question for i in items], name
        if m["id_col"] is None:
            continue
        found = [row[_index(m["id_col"])] for row in below]
        ids = [c for c in found if isinstance(c, str) and re.fullmatch(r"[A-Z]{2,3}-\d{2}", c)]
        assert len(ids) == len(set(ids)) == 20, name  # section titles in the ID column are not IDs
        if name != "v10.xlsx":
            assert ids == [i.code for i in items], name


def test_v01_is_clean(built: Built) -> None:
    ws = _sheet(built, "v01.xlsx")
    assert ws.title == "Sheet1" and (ws.max_row, ws.max_column) == (21, 3)  # header, 20 questions
    assert not ws.merged_cells.ranges
    assert [row[1:] for row in ws.iter_rows(min_row=2, values_only=True)] == [(None, None)] * 20


def test_v02_has_a_title_block_above_a_header_on_row_6(built: Built) -> None:
    ws = _sheet(built, "v02.xlsx")
    assert ws["A1"].value.startswith("Northbeam Health") and ws["A4"].value == "Version 3"
    assert [ws[f"A{r}"].value for r in (3, 5)] == [None, None]
    assert [c.value for c in ws[6]] == ["ID", "Question", "Response", "Notes"]
    assert (ws["A7"].value, ws["B7"].value) == (_first_20()[0].code, _first_20()[0].question)
    assert ws.max_row == 26


def test_v03_has_a_text_only_cover_sheet_ahead_of_the_table(built: Built) -> None:
    out, _ = built
    wb = openpyxl.load_workbook(str(out / "v03.xlsx"))
    assert wb.sheetnames == ["Cover", "Security"] and wb.active.title == "Cover"
    cover = [c for row in wb["Cover"].iter_rows() for c in row if c.value is not None]
    assert cover and all(isinstance(c.value, str) and c.column == 1 for c in cover)  # prose, no table
    assert [c.value for c in wb["Security"][1]][1:] == [None, None, None]  # a banner above the header


def test_v04_has_a_two_row_header_with_response_merged_over_yes_no_and_details(
    built: Built,
) -> None:
    ws = _sheet(built, "v04.xlsx")
    assert {str(r) for r in ws.merged_cells.ranges} == {"A3:A4", "B3:C3"}
    assert [ws["B3"].value, ws["B4"].value, ws["C4"].value] == ["Response", "Yes/No", "Details"]
    assert ws["A5"].value == _first_20()[0].question  # the data starts under the second header row
    assert ws.max_row == 24


def test_v05_has_merged_bold_section_rows_and_a_blank_row_between_sections(
    built: Built,
) -> None:
    ws = _sheet(built, "v05.xlsx")
    rows = list(ws.iter_rows(min_row=2))
    titles = ["GOVERNANCE", "ACCESS CONTROL", "DATA SECURITY"]
    sections = [row[0] for row in rows if row[0].value in titles]
    assert [c.value for c in sections] == titles
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert merged == {f"A{c.row}:D{c.row}" for c in sections}
    assert all(c.font.bold for c in sections)
    assert sections[0].row == 2  # the first section starts right under the header
    blank = [row[0].row for row in rows if all(c.value is None for c in row)]
    assert blank == [c.row - 1 for c in sections[1:]]  # one empty row before every later section


def test_v06_has_answers_filled_in_for_the_first_five_rows_only(built: Built) -> None:
    rows = list(_sheet(built, "v06.xlsx").iter_rows(min_row=2, values_only=True))
    assert [r[1] for r in rows[:5]] == ["Yes", "Yes", "Yes", "No", "Yes"]
    assert [r[1] for r in rows[5:]] == [None] * 15
    assert any(r[2] for r in rows[:5]) and not any(r[2] for r in rows[5:])  # the comments go with them


def test_v07_is_semicolon_delimited_and_needs_no_quotes(built: Built) -> None:
    out, _ = built
    text = (out / "v07.csv").read_bytes().decode("utf-8")
    assert text.startswith("Question;Answer;Comment\r\n") and '"' not in text
    assert {len(r) for r in _grid(out / "v07.csv", None)} == {3}
    assert any("," in r[0] for r in _grid(out / "v07.csv", None))  # a comma that is just text here


def test_v08_has_comma_delimited_questions_that_span_lines_inside_quotes(
    built: Built,
) -> None:
    out, _ = built
    text = (out / "v08.csv").read_bytes().decode("utf-8")
    rows = _grid(out / "v08.csv", None)
    assert {len(r) for r in rows} == {4} and len(rows) == 21
    spanning = [r[1] for r in rows[1:] if "\n" in r[1]]
    assert len(spanning) >= 10 and all(f'"{q}"' in text for q in spanning)
    assert len(text.splitlines()) > len(rows)  # more physical lines than records


def test_v09_has_spanish_headers_over_the_english_questions(built: Built) -> None:
    ws = _sheet(built, "v09.xlsx")
    assert [c.value for c in ws[1]] == ["Pregunta", "Respuesta", "Comentarios"]
    assert ws["A2"].value == _first_20()[0].question


def test_v10_has_its_question_third_between_extra_columns_and_ids_in_another_format(
    built: Built,
) -> None:
    rows = list(_sheet(built, "v10.xlsx").iter_rows(min_row=2, values_only=True))
    assert all(isinstance(r[0], int) and 1 <= r[0] <= 5 for r in rows)  # Weight
    ids = [r[1] for r in rows]
    assert ids[:6] == [f"GV-{n:02d}" for n in range(1, 7)]
    assert [i for i in ids if i.startswith("AC-")] == [f"AC-{n:02d}" for n in range(1, 11)]
    assert [i for i in ids if i.startswith("DS-")] == [f"DS-{n:02d}" for n in range(1, 5)]
    assert all(r[5] for r in rows) and all(r[3] is None and r[4] is None for r in rows)  # Owner only


def test_every_xlsx_variant_is_a_normalized_zip(built: Built) -> None:
    out, expected = built
    for name in (n for n in expected if n.endswith(".xlsx")):  # normalize_zip: no zlib, no tool name or clock
        with zipfile.ZipFile(out / name) as z:
            assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_STORED}, name
            assert {i.create_system for i in z.infolist()} == {3}, name
            assert {i.date_time for i in z.infolist()} == {(2026, 1, 1, 0, 0, 0)}, name
            assert b"<Application>" not in z.read("docProps/app.xml"), name
            assert b"2026-01-01T00:00:00Z" in z.read("docProps/core.xml"), name


def test_bytes_do_not_depend_on_the_clock(tmp_path: Path) -> None:
    build_all(tmp_path / "first")
    time.sleep(1.1)  # zip members and document properties stamp whole seconds
    build_all(tmp_path / "second")
    for p in sorted((tmp_path / "first").iterdir()):
        assert p.read_bytes() == (tmp_path / "second" / p.name).read_bytes(), p.name


def test_csv_records_end_in_crlf_and_a_line_break_inside_a_question_is_a_bare_lf(
    built: Built,
) -> None:
    out, _ = built
    for name in ("v07.csv", "v08.csv"):
        raw = (out / name).read_bytes()
        assert raw.isascii() and raw.count(b"\r\n") == 21, name  # the header and 20 records
        assert b"\r" not in raw.replace(b"\r\n", b""), name
    assert b"\n" in (out / "v08.csv").read_bytes().replace(b"\r\n", b"")


def test_main_builds_into_data_mapper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mapper_variants, "OUT", tmp_path / "mapper")
    mapper_variants.main()
    assert sorted(p.name for p in (tmp_path / "mapper").iterdir()) == sorted([*NAMES, "expected.json"])


def test_the_mapper_stage_passes_on_the_committed_files() -> None:
    assert STAGES["mapper"]("dev") == []
    assert validate.main(["mapper"]) == 0


@pytest.fixture
def committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of data/mapper that the stage reads instead of the real one."""
    shutil.copytree(DATA / "mapper", tmp_path / "data" / "mapper")
    monkeypatch.setattr(validate, "DATA", tmp_path / "data")
    return tmp_path / "data" / "mapper"


def test_the_mapper_stage_flags_a_changed_file_a_missing_file_and_a_stale_expected_json(
    committed: Path,
) -> None:
    assert STAGES["mapper"]("dev") == []
    (committed / "v01.xlsx").write_bytes((committed / "v01.xlsx").read_bytes() + b"\0")
    (committed / "v07.csv").unlink()
    expected = committed / "expected.json"
    expected.write_text(expected.read_text(encoding="utf-8").replace('"header_row": 6', '"header_row": 7'))
    assert STAGES["mapper"]("dev") == [
        "mapper/v01.xlsx is stale: run python -m datakit.mapper_variants",
        "mapper/v07.csv is stale: run python -m datakit.mapper_variants",
        "mapper/expected.json is stale",
    ]


def test_the_mapper_stage_flags_a_missing_expected_json(committed: Path) -> None:
    (committed / "expected.json").unlink()
    assert STAGES["mapper"]("dev") == ["mapper/expected.json is stale"]
