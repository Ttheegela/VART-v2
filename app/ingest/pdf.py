"""PDF text layer to lines (spec 6.4). Visual lines are joined into paragraphs, because wrapping is not a
paragraph break; a new paragraph starts at a font-size change, a bullet, or a gap wider than 1.6 line
heights after a line that ends a sentence (or before one that starts with a capital or a digit). Measured on
the dev pack's PDFs: 5 mm pitch inside a paragraph, 6-7 mm between paragraphs and rows (Plan 2 addendum)."""

import re
import threading
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from app.contracts import Line
from app.ingest.parse import IngestError
from app.text import normalize

MAX_PAGES = 200  # spec 9: 20,000 lines is about 200 pages
MIN_CHARS = 20  # fewer letters than this in the whole file: a scan with no text layer
MAX_PARAGRAPH = 1_500  # characters after which a sentence end starts a new paragraph even without a gap
MIN_SIZE = 1.0  # text under 1 pt cannot be read on the page (Plan 3 adversary-3 M4). Invisible render mode is
# kept on purpose: OCR'd scans put their whole text layer there, and the reader sees it as the page image.
GAP = 1.6  # a vertical gap wider than this many font sizes can start a paragraph
_TERMINAL = re.compile(r"[.!?:;][\"')\]]?$")
_BULLET = re.compile(r"^(?:[-*\N{BULLET}\N{BLACK SMALL SQUARE}\N{EN DASH}]\s|\(?[0-9a-z]{1,3}[.)]\s)")
# ponytail: global pdfium lock (pdfium is not thread-safe); process isolation if uploads ever queue up.
_PDFIUM_LOCK = threading.Lock()


@dataclass(frozen=True)
class Visual:
    text: str
    size: float  # font size of the line's first character
    bottom: float  # loose-box bottom of that character (PDF points, origin bottom-left)
    page: int


def _visual_lines(pdf: pdfium.PdfDocument) -> list[Visual]:
    out: list[Visual] = []
    for number in range(len(pdf)):
        page = pdf[number]
        textpage = page.get_textpage()
        try:
            text = textpage.get_text_range()
            exact = len(text) == textpage.count_chars()  # char index == text index (no surrogate pairs)
            start = 0
            for part in text.split("\r\n"):
                if part.strip():
                    i = start + len(part) - len(part.lstrip())
                    size = round(pdfium_c.FPDFText_GetFontSize(textpage.raw, i), 1) if exact else 0.0
                    bottom = textpage.get_charbox(i, loose=True)[1] if exact else 0.0
                    # the size on the page: the font size times the text matrix and CTM scale (Tf is not it)
                    m = pdfium_c.FS_MATRIX()
                    pdfium_c.FPDFText_GetMatrix(textpage.raw, i, m)
                    shown = pdfium_c.FPDFText_GetFontSize(textpage.raw, i) * abs(m.a * m.d - m.b * m.c) ** 0.5
                    # ponytail: the line's first character only; a tiny phrase inside a readable line is a gap
                    if not (exact and shown < MIN_SIZE):
                        out.append(Visual(part.strip(), size, bottom, number))
                start += len(part) + 2
        finally:
            textpage.close()
            page.close()
    return out


def _starts_paragraph(prev: Visual, cur: Visual) -> bool:
    if abs(cur.size - prev.size) > 0.5 or _BULLET.match(cur.text):
        return True
    ends = _TERMINAL.search(prev.text) is not None
    opens = cur.text[:1].isupper() or cur.text[:1].isdigit()
    if cur.page != prev.page:
        return ends and opens  # a paragraph may run across a page break
    return prev.bottom - cur.bottom > GAP * max(prev.size, 1.0) and (ends or opens)


def _long_enough_to_split(prev: Visual, cur: Visual, length: int) -> bool:
    """With even line spacing no gap ever starts a paragraph; past MAX_PARAGRAPH characters a sentence end
    does (a paragraph is one line, so a page-long one would carry the flags of every sentence in it)."""
    return (
        length > MAX_PARAGRAPH
        and _TERMINAL.search(prev.text) is not None
        and (cur.text[:1].isupper() or cur.text[:1].isdigit())
    )


def join_lines(visual: list[Visual]) -> list[tuple[str, float]]:
    """Paragraphs as (text, font size). pdfium already joins a word hyphenated across a line break and marks
    the hyphen U+FFFE; it becomes a plain hyphen, so 'multi-factor' survives (a syllable break reads
    'quar-terly', which the model then quotes as stored). Adversary F15."""
    groups: list[list[str]] = []  # the visual lines of each paragraph; joined once
    sizes: list[float] = []
    length = 0
    for i, cur in enumerate(visual):
        if (
            i
            and not _starts_paragraph(visual[i - 1], cur)
            and not _long_enough_to_split(visual[i - 1], cur, length)
        ):
            groups[-1].append(cur.text)
            length += len(cur.text) + 1
        else:
            groups.append([cur.text])
            sizes.append(cur.size)
            length = len(cur.text)
    paras = [(" ".join(g), s) for g, s in zip(groups, sizes, strict=True)]
    return [(t.replace(chr(0xFFFE), "-"), s) for t, s in paras]


def pdf_lines(data: bytes) -> list[Line]:
    with _PDFIUM_LOCK:
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            if "password" in str(exc).lower():
                raise IngestError("This PDF is password protected; upload an unprotected copy.") from exc
            raise IngestError("This PDF could not be read.") from exc
        try:
            if len(pdf) > MAX_PAGES:
                raise IngestError(f"PDFs may have at most {MAX_PAGES} pages.")
            visual = _visual_lines(pdf)
        finally:
            pdf.close()
    if sum(ch.isalpha() for v in visual for ch in v.text) < MIN_CHARS:
        raise IngestError("This PDF has no text layer (it may be a scan); upload a PDF with selectable text.")
    paras = join_lines(visual)
    weight: dict[float, int] = {}
    for text, size in paras:
        weight[size] = weight.get(size, 0) + len(text)
    body = max(weight, key=lambda s: (weight[s], -s))
    lines = [Line(normalize(t), "heading" if s > body + 1 else "text") for t, s in paras]
    return [x for x in lines if x.text]
