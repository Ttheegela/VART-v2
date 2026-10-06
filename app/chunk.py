"""Chunk (spec 6.4): heading-aware passages over line ranges, one passage per record row, and the chunk
flags from app/patterns.py. A chunk's text is its lines joined by newlines, so a passage splits back into
its lines."""

from collections.abc import Sequence

from app.contracts import ChunkSpec, Flag, Line
from app.patterns import INJECTION, NEGATION, PLACEHOLDER

# Plan 2 planning probe on the dev pack: recall@8 0.95 at 120 words, 0.93 at 60, 0.92 at 40.
MAX_WORDS = 120


def flags_of(text: str) -> tuple[Flag, ...]:
    found: list[Flag] = []
    if NEGATION.search(text):
        found.append("negation")
    if PLACEHOLDER.search(text):
        found.append("placeholder")
    if INJECTION.search(text):
        found.append("injection")
    return tuple(found)


def chunk_lines(lines: Sequence[Line]) -> list[ChunkSpec]:
    """Line numbers are 1-based. A heading line closes the running passage and labels the next ones; it is not
    part of any passage. Before the first heading, passages are labelled with the document's first line. The
    prompts print that label with every passage, so a label that matches INJECTION flags each passage beneath
    it `injection`; a negation or placeholder in a label does not spread to the lines beneath it."""
    chunks: list[ChunkSpec] = []
    title = lines[0].text if lines else None
    heading: str | None = None
    run: list[tuple[int, Line]] = []

    def flags(text: str) -> tuple[Flag, ...]:
        found = flags_of(text)
        label = heading or title
        if label and INJECTION.search(label) and "injection" not in found:
            return (*found, "injection")
        return found

    def flush() -> None:
        if run:
            text = "\n".join(line.text for _, line in run)
            chunks.append(ChunkSpec(run[0][0], run[-1][0], text, heading or title, flags(text), None, False))
            run.clear()

    for n, line in enumerate(lines, 1):
        if line.kind == "heading":
            flush()
            heading = line.text
        elif line.kind == "record":
            flush()
            chunks.append(ChunkSpec(n, n, line.text, heading or title, flags(line.text), line.as_of, True))
        else:
            if run and sum(len(x.text.split()) for _, x in run) + len(line.text.split()) > MAX_WORDS:
                flush()
            run.append((n, line))
    flush()
    return chunks
