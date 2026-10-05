from pathlib import Path

import pytest
from fpdf import FPDF

from app.ingest.parse import IngestError, parse
from app.ingest.pdf import Visual, join_lines
from app.text import contains, normalize
from datakit.extract import lines_of
from datakit.schemas import Facts, Key, load_yaml

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "data" / "dev"
FACTS = load_yaml(DEV / "facts.yaml", Facts)
PDFS = [d for d in FACTS.documents if d.format == "pdf"]


@pytest.mark.parametrize("spec", PDFS, ids=lambda d: d.id)
def test_dev_pdfs_hold_the_reference_text_split_into_paragraphs(spec) -> None:  # type: ignore[no-untyped-def]
    path = DEV / "docs" / spec.filename
    lines = [x.text for x in parse(spec.filename, path.read_bytes()).lines]
    assert normalize(" ".join(lines)) == lines_of(path)[0]  # nothing lost, nothing added
    assert len(lines) > 15  # paragraphs, not one joined page


def test_every_key_quote_from_a_pdf_sits_in_exactly_one_line() -> None:
    # The soc2 opinion sentence wraps across two visual lines ("...for the period" / "2025-07-01 ...").
    lines = {
        d.id: [x.text for x in parse(d.filename, (DEV / "docs" / d.filename).read_bytes()).lines]
        for d in PDFS
    }
    for name in ("vsq-a", "mvsp-b"):
        for item in load_yaml(DEV / "key" / f"{name}.yaml", Key).items:
            for e in item.evidence:
                if e.doc in lines:
                    assert sum(contains(x, e.quote) for x in lines[e.doc]) == 1, (item.code, e.quote)


def test_headings_are_found_by_font_size() -> None:
    soc2 = next(d for d in PDFS if d.id == "soc2")
    lines = parse(soc2.filename, (DEV / "docs" / soc2.filename).read_bytes()).lines
    assert [x.text for x in lines if x.kind == "heading"][:2] == [
        "SOC 2 Type II Report Summary",
        "Independent Service Auditor's Opinion",
    ]


def v(text: str, size: float = 10.5, bottom: float = 700.0, page: int = 0) -> Visual:
    return Visual(text, size, bottom, page)


def test_paragraph_rules() -> None:
    lines = [
        v("Title", size=15, bottom=780),
        v("A sentence that wraps", bottom=760),
        v("onto a second line.", bottom=746),
        v("Next paragraph after a gap.", bottom=726),
        v("- a bullet", bottom=712),
        v("Ends mid sentence and", bottom=100),
        v("continues on the next page.", bottom=760, page=1),
    ]
    assert [t for t, _ in join_lines(lines)] == [
        "Title",
        "A sentence that wraps onto a second line.",
        "Next paragraph after a gap.",
        "- a bullet",
        "Ends mid sentence and continues on the next page.",
    ]


def _pdf(*rows: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10.5)
    for row in rows:
        pdf.cell(0, 5, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_a_word_hyphenated_across_lines_keeps_a_plain_hyphen() -> None:
    # pdfium joins the two halves itself and marks the hyphen U+FFFE (adversary F15).
    lines = parse("h.pdf", _pdf("MFA is required for multi-", "factor sign-in on admin accounts.")).lines
    assert [x.text for x in lines] == ["MFA is required for multi-factor sign-in on admin accounts."]


def test_a_scan_or_an_empty_pdf_is_refused() -> None:
    blank = FPDF()
    blank.add_page()
    with pytest.raises(IngestError, match="no text layer"):
        parse("scan.pdf", bytes(blank.output()))


def test_a_password_protected_pdf_is_refused() -> None:
    pdf = FPDF()
    pdf.set_encryption(owner_password="owner", user_password="user")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 5, "Text that would otherwise be long enough to read.")
    with pytest.raises(IngestError, match="password"):
        parse("locked.pdf", bytes(pdf.output()))


def test_a_pdf_with_even_line_spacing_still_splits_into_paragraphs_at_sentence_ends() -> None:
    lines = [
        v(f"Sentence number {i} ends here.", bottom=780 - 5 * i) for i in range(100)
    ]  # 3,000+ characters
    joined = [t for t, _ in join_lines(lines)]
    assert len(joined) > 1
    assert all(len(t) < 1_500 + 40 for t in joined)
    assert " ".join(joined) == " ".join(x.text for x in lines)


def test_a_long_paragraph_without_sentence_ends_is_not_split() -> None:
    lines = [v(f"and the clause number {i} continues", bottom=780 - 5 * i) for i in range(80)]
    assert len(join_lines(lines)) == 1
