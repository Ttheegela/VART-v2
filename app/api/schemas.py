"""The HTTP contract (spec 6.12), frozen after Plan 3's adversary checkpoint 1. Every request and response
body is one of these models; web/src/lib/api-types.ts is generated from them. Changing one needs the lead's OK
and a line in docs/CONTRACTS.md (HTTP section)."""

import unicodedata
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic.json_schema import SkipJsonSchema

from app.contracts import DropReason

MAX_ANSWER_CHARS = 4000  # an interview answer (engine adversary-3 I3: statements bypass the line limit)
MAX_EDIT_CHARS = 4000  # an edited answer text
MAX_REASON_CHARS = 500  # a "not applicable" reason
MAX_LINES_PER_READ = 200  # GET /api/documents/{id}/lines
MAX_QUESTIONNAIRES = 5  # per workspace (adversary-1 I3: questionnaire bytes are the one stored upload)
MAX_QUESTIONNAIRE_BYTES = 1024 * 1024  # 1 MB per questionnaire file; a 150-item questionnaire is tens of KB


def clean_text(value: str) -> str:
    """Drop lone surrogates and NUL: JSON can carry both, Postgres refuses both (a 500, triage row 41)."""
    return "".join(ch for ch in value if ch != chr(0) and unicodedata.category(ch) != "Cs")


def _clean_and_strip(value: object) -> object:
    return clean_text(value).strip() if isinstance(value, str) else value


CleanText = Annotated[str, AfterValidator(clean_text)]
# Pre-flight P6: StringConstraints check the length before an AfterValidator or strip_whitespace runs, so
# "   " passed as "". These clean and strip first (BeforeValidator), then the bounds apply: blank or too long
# is a 422.
AnswerText = Annotated[
    str, BeforeValidator(_clean_and_strip), StringConstraints(min_length=1, max_length=MAX_ANSWER_CHARS)
]
EditText = Annotated[
    str, BeforeValidator(_clean_and_strip), StringConstraints(min_length=1, max_length=MAX_EDIT_CHARS)
]
ReasonText = Annotated[
    str, BeforeValidator(_clean_and_strip), StringConstraints(min_length=1, max_length=MAX_REASON_CHARS)
]
Label = Literal["verified", "partial", "conflict", "unknown", "user_confirmed", "na"]
Value = Literal["Yes", "No", "Partial"]
Column = Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,3}$")]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorOut(BaseModel):
    detail: str


ERRORS: dict[int | str, dict[str, object]] = {
    403: {
        "model": ErrorOut,
        "description": "A state-changing request from another site (POST, PUT, PATCH, DELETE)",
    },
    404: {"model": ErrorOut, "description": "Unknown id, another workspace's id, or the workspace is gone"},
    409: {"model": ErrorOut, "description": "The action conflicts with the item's state"},
    429: {"model": ErrorOut, "description": "A per-network limit or the model budget; see Retry-After"},
    503: {"model": ErrorOut, "description": "The demo is full, or model calls are off"},
}
# Review I-1: operations that refuse input with a sentence ({"detail": str}) as well as FastAPI's list form.
# Declared as a raw schema: FastAPI's HTTPValidationError is a schema dict, not a model.
SENTENCE_422: dict[int | str, dict[str, object]] = {
    422: {
        "description": "Refused input: a sentence, or FastAPI's validation list",
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorOut"},
                        {"$ref": "#/components/schemas/HTTPValidationError"},
                    ]
                }
            }
        },
    }
}


# ------------------------------------------------------------------ questionnaires
class Mapping(BaseModel):
    """Where the questionnaire lives in its file. Columns are letters for xlsx and csv alike (A is the first
    column); header_row is 1-based. topic_col is optional: without it, the last section row is the topic."""

    model_config = ConfigDict(extra="forbid")
    sheet: Annotated[CleanText, StringConstraints(max_length=31)] | None  # Excel's sheet-name limit
    header_row: int = Field(ge=1, le=1000)
    id_col: Column | None
    question_col: Column
    answer_col: Column
    comments_col: Column | None
    topic_col: Column | None = None
    scope: Annotated[CleanText, StringConstraints(max_length=32)] | None = (
        None  # Plan 6B: a csf questionnaire's scope
    )


class PreviewRow(BaseModel):
    row: int
    id: str | None
    question: str
    topic: str | None
    answer: str | None


class ItemOut(_Out):
    id: uuid.UUID
    position: int
    row_ref: str
    code: str | None
    topic: str | None
    question: str
    csf_id: str | None


class QuestionnaireOut(_Out):
    id: uuid.UUID
    filename: str
    source: Literal["sample", "upload", "drive", "csf"]
    format: Literal["xlsx", "csv", "builtin"]
    sheets: list[str]
    detected: Mapping | None  # what the mapper found; None when it found no question column
    mapping: Mapping | None  # the confirmed mapping; None until PUT .../mapping (samples: set at once)
    preview: list[PreviewRow]  # the first 8 data rows under `mapping or detected`
    item_count: int
    latest_run_id: uuid.UUID | None
    created_at: datetime


class QuestionnaireDetail(QuestionnaireOut):
    items: list[ItemOut]


# ------------------------------------------------------------------ documents
Kind = Literal["policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other"]
Scope = Literal["internal-systems", "customer-product", "production", "employees", "vendors-and-contractors"]


class DocumentOut(_Out):
    id: uuid.UUID
    filename: str
    source: Literal["sample", "upload", "drive", "statement"]
    kind: Kind
    status: Literal["final", "draft"]
    effective_date: date | None
    scope: Scope | None
    evidence_allowed: bool
    metadata_source: Literal["rule", "model", "user"]
    line_count: int
    created_at: datetime


class DocumentPatch(BaseModel):
    """A visitor override (spec 5 step 3): only the fields sent change; metadata_source becomes 'user'."""

    model_config = ConfigDict(extra="forbid")
    # Pre-flight P8: kind, status and evidence_allowed may be left out but not sent as null (NOT NULL
    # columns). SkipJsonSchema keeps null out of the schema; the validator refuses it. effective_date and
    # scope may be cleared.
    kind: Kind | SkipJsonSchema[None] = None
    status: Literal["final", "draft"] | SkipJsonSchema[None] = None
    effective_date: date | None = None
    scope: Scope | None = None
    evidence_allowed: bool | SkipJsonSchema[None] = None

    @field_validator("kind", "status", "evidence_allowed")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("may be left out, but not null")
        return value


class DocumentUpdated(DocumentOut):
    redecided: int  # answers whose label, value or citations changed (decide again, no model call)


class LineOut(BaseModel):
    n: int
    text: str


class LinesOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    lines: list[LineOut]


# ------------------------------------------------------------------ runs and answers
class RunOut(_Out):
    id: uuid.UUID
    questionnaire_id: uuid.UUID
    status: Literal["running", "done", "failed"]
    total: int
    done: int
    cost_usd: float
    models: dict[str, str]
    prompt_versions: dict[str, str]
    started_at: datetime
    finished_at: datetime | None


class AnswerSummary(BaseModel):
    """One grid row's answer (design.md: id, label, conf, src, question, answer, approval)."""

    id: uuid.UUID
    item_id: uuid.UUID
    label: Label
    value: Value | None
    text: str
    confidence: float
    sources: int  # cited documents; 1 for confirmed by you (the statement)
    approved: bool
    edited: bool
    statement_id: uuid.UUID | None


class RunRow(BaseModel):
    item: ItemOut
    answer: AnswerSummary | None  # None while the item is pending


class RunRowsOut(BaseModel):
    run: RunOut
    rows: list[RunRow]  # every item, in questionnaire order


class StepOut(BaseModel):
    run: RunOut
    answered: list[RunRow]  # the rows this step wrote (empty on a finished run)


class ContextLine(BaseModel):
    n: int
    text: str
    cited: bool


class CitationOut(BaseModel):
    """A cited line, re-read from the stored document (spec 2) with two lines of context each side."""

    document_id: uuid.UUID
    filename: str
    kind: Kind
    status: Literal["final", "draft"]
    date: date | None  # effective date, audit period end, or the record's as-of date
    scope: Scope | None
    line: int
    quote: str
    stance: Literal["yes", "no", "partial"]
    found_in_source: bool  # the quote re-read from document_lines; False is a bug, shown, never hidden
    context: list[ContextLine]


class DroppedOut(BaseModel):
    reason: DropReason
    document_id: uuid.UUID
    filename: str
    line: int | None
    sentence: str  # why, in words; dropped text is never shown as a quote (design.md)


class ConflictSideOut(BaseModel):
    stance: Literal["yes", "no"]
    date: date | None
    citations: list[int]  # indexes into AnswerDetail.citations


class ConflictOut(BaseModel):
    rule: Literal["date", "documents-disagree"]
    sides: list[ConflictSideOut]  # newer record first for the date rule


class AnswerDetail(AnswerSummary):
    item: ItemOut
    citations: list[CitationOut]
    dropped: list[DroppedOut]
    conflict: ConflictOut | None
    scope_note: str | None
    statement_lines: list[LineOut]  # confirmed by you: the visitor's stored (redacted) answer


class AnswerEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: EditText


class NotApplicableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: ReasonText


class ApprovedCount(BaseModel):
    approved: int
    skipped_edited: int = 0  # edited verified answers left for a look (adversary-1 M5)


# ------------------------------------------------------------------ interview
class SuggestionOut(_Out):
    id: uuid.UUID
    item_id: uuid.UUID
    code: str | None
    question: str
    label: Literal["verified", "partial"]
    value: Value | None
    text: str
    status: Literal["open", "accepted", "dismissed"]


class QuestionOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    item_ids: list[uuid.UUID]
    codes: list[str | None]
    reason: Literal["conflict", "unknown", "partial"]
    text: str  # the question to ask (for a conflict, the drafted "Which is current?" question)
    follow_up: str | None  # set while status is follow_up
    status: Literal["open", "follow_up", "answered", "skipped"]
    asked_count: int
    high_weight: bool
    suggestions: list[SuggestionOut]  # open fills this question's answer produced


class AnswerQuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: AnswerText


class AnswerQuestionOut(BaseModel):
    question: QuestionOut
    answer: AnswerSummary | None  # the confirmed answer; None when a follow-up is asked
    suggestions: list[SuggestionOut]


# ------------------------------------------------------------------ audit
class AuditEventOut(_Out):
    at: datetime
    actor: str
    action: str
    ref: str | None
    detail: dict[str, object]
