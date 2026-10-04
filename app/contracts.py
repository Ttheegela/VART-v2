"""Frozen interfaces between the engine units (spec 6.2). Changing a type here needs the lead's OK, an entry
in docs/CONTRACTS.md and, when a recorded prompt depends on it, a re-recording."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from typing import Any, Literal

LineKind = Literal["text", "heading", "record"]
DocKind = Literal["policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other"]
DocStatus = Literal["final", "draft"]
Flag = Literal["negation", "placeholder", "injection"]
StanceLabel = Literal["yes", "no", "partial", "irrelevant"]
CitedStance = Literal["yes", "no", "partial"]
Label = Literal["verified", "partial", "conflict", "unknown"]
ItemLabel = Literal["verified", "partial", "conflict", "unknown", "user_confirmed", "na"]
Value = Literal["Yes", "No", "Partial"]
DropReason = Literal[
    "containment", "quote-length", "record-field", "not-evidence", "placeholder", "injection"
]
ConflictRule = Literal["date", "documents-disagree"]
SCOPES = ("internal-systems", "customer-product", "production", "employees", "vendors-and-contractors")
Spend = Callable[[str], bool]


class BudgetExhausted(Exception):
    """The workspace or global model budget refused a call."""


@dataclass(frozen=True)
class Line:
    text: str
    kind: LineKind = "text"
    as_of: date | None = None


@dataclass(frozen=True)
class ParsedDocument:
    format: Literal["pdf", "docx", "xlsx", "csv", "md", "txt"]
    lines: tuple[Line, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocMeta:
    kind: DocKind
    status: DocStatus
    effective_date: date | None
    scope: str | None
    evidence_allowed: bool
    source: Literal["rule", "model"]


@dataclass(frozen=True)
class ChunkSpec:
    line_start: int
    line_end: int
    text: str
    heading: str | None
    flags: tuple[Flag, ...]
    as_of: date | None
    record: bool


@dataclass(frozen=True)
class DocInfo:
    id: str
    filename: str
    kind: DocKind
    status: DocStatus
    effective_date: date | None
    scope: str | None
    evidence_allowed: bool


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    doc: DocInfo
    line_start: int
    lines: tuple[str, ...]
    heading: str | None
    flags: tuple[Flag, ...]
    as_of: date | None
    record: bool

    @property
    def line_end(self) -> int:
        return self.line_start + len(self.lines) - 1


@dataclass(frozen=True)
class Dropped:
    chunk_id: str
    document_id: str
    filename: str
    reason: DropReason
    quote: str = ""


@dataclass(frozen=True)
class Retrieval:
    passages: tuple[Passage, ...]
    dropped: tuple[Dropped, ...]


@dataclass(frozen=True)
class Stance:
    passage: int
    stance: StanceLabel
    quote: str
    note: str


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_id: str
    filename: str
    line_start: int
    line_end: int
    quote: str
    stance: CitedStance
    note: str = ""


@dataclass(frozen=True)
class ConflictSide:
    stance: Literal["yes", "no"]
    citations: tuple[Citation, ...]
    date: date | None


@dataclass(frozen=True)
class Conflict:
    rule: ConflictRule
    sides: tuple[ConflictSide, ConflictSide]


@dataclass(frozen=True)
class Decision:
    label: Label
    value: Value | None
    citations: tuple[Citation, ...]
    dropped: tuple[Dropped, ...]
    conflict: Conflict | None
    scope_note: str | None
    confidence: float


@dataclass(frozen=True)
class Draft:
    text: str
    source: Literal["model", "template", "none"]
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemInput:
    key: str
    question: str
    topic: str | None


@dataclass(frozen=True)
class ItemResult:
    item: ItemInput
    retrieval: Retrieval
    stances: tuple[Stance, ...]
    decision: Decision
    draft: Draft
    cost_usd: float
    latency_ms: int


@dataclass(frozen=True)
class OpenItem:
    item: ItemInput
    label: ItemLabel
    asked: int = 0  # times the person was already asked (the one follow-up makes it 2)
    prompt: str = ""  # the drafted text; for a conflict it is the question to ask


OpenLabel = Literal["conflict", "unknown", "partial"]


@dataclass(frozen=True)
class QueueEntry:
    key: str
    reason: OpenLabel
    question: str
    high_weight: bool


@dataclass(frozen=True)
class Suggestion:
    key: str
    decision: Decision


def jsonable(obj: Any) -> Any:
    """Dataclasses, tuples and dates as plain JSON values (for answers.citations, the eval results, logs)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
