"""Shapes of the dev-data files. Everything under data/ is validated against these before evals trust it."""

import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

DocKind = Literal["policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other"]
Stance = Literal["yes", "no", "partial"]
Flag = Literal["negation", "placeholder", "injection"]
TrapKind = Literal[
    "date",
    "disagree",
    "scope",
    "negation",
    "honest_negative",
    "placeholder",
    "draft_only",
    "planned_only",
    "injection",
    "must_ask",
    "fills",
]
Label = Literal["verified", "partial", "conflict", "unknown"]
Value = Literal["Yes", "No", "Partial"]
# A document with no scope applies everywhere.
# Only two different scopes from this list are a scope difference.
SCOPES = ("internal-systems", "customer-product", "production", "employees", "vendors-and-contractors")
Scope = Literal["internal-systems", "customer-product", "production", "employees", "vendors-and-contractors"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Company(_Strict):
    name: str
    legal_name: str
    domain: str
    product: str
    employees: int
    hosting: str


class Person(_Strict):
    name: str
    role: str
    email: str


class DocSpec(_Strict):
    id: str
    filename: str
    format: Literal["docx", "pdf", "xlsx", "md"]
    kind: DocKind
    status: Literal["final", "draft"] = "final"
    effective_date: date | None = None
    period_end: date | None = None  # audit reports: end of the period reviewed
    as_of: date | None = None  # records
    scope: Scope | None = None
    evidence_allowed: bool = True
    source_template: str | None = None  # JupiterOne template path when adapted

    @property
    def dated(self) -> date | None:
        return self.as_of or self.period_end or self.effective_date


class Control(_Strict):
    id: str
    topic: str
    truth: str


class Statement(_Strict):
    id: str
    doc: str
    text: str
    control: str | None
    stance: Stance
    flags: tuple[Flag, ...] = ()


class Trap(_Strict):
    id: str
    kind: TrapKind
    statements: tuple[str, ...] = ()
    # must_ask: uncovered controls; fills: (answered control, filled controls...);
    # injection: the controls it targets
    controls: tuple[str, ...] = ()
    note: str


class Facts(_Strict):
    pack: str
    company: Company
    buyer: str
    people: tuple[Person, ...]
    documents: tuple[DocSpec, ...]
    controls: tuple[Control, ...]
    statements: tuple[Statement, ...]
    traps: tuple[Trap, ...]

    def doc(self, doc_id: str) -> DocSpec:
        return next(d for d in self.documents if d.id == doc_id)

    def control(self, control_id: str) -> Control:
        return next(c for c in self.controls if c.id == control_id)

    def statement(self, statement_id: str) -> Statement:
        return next(s for s in self.statements if s.id == statement_id)

    def statements_for(self, control_id: str) -> list[Statement]:
        return [s for s in self.statements if s.control == control_id]


class SelectionItem(_Strict):
    code: str
    section: str
    question: str
    source: str  # "vsaq:<file>#<id>" or "mvsp:<label>"
    csf_id: str | None
    control: str


class Selection(_Strict):
    questionnaire: str
    title: str
    buyer: str
    items: tuple[SelectionItem, ...]


class KeyEvidence(_Strict):
    doc: str
    quote: str
    stance: Stance


class KeyItem(_Strict):
    code: str
    expected_label: Label
    expected_value: Value | None
    must_ask: bool
    evidence: tuple[KeyEvidence, ...]
    conflict_trap: str | None
    scope_note_expected: bool
    honest_negative: bool
    traps: tuple[str, ...]
    fills: tuple[str, ...]


class Key(_Strict):
    pack: str
    questionnaire: str
    items: tuple[KeyItem, ...]


class GapOutcome(_Strict):
    csf_id: str
    control: str


class GapFacts(_Strict):
    """data/<pack>/gap/facts.yaml: what only the CSF gap check adds to the pack's fact sheet (datakit.gap)."""

    pack: str
    documents: tuple[DocSpec, ...] = ()
    controls: tuple[Control, ...] = ()
    statements: tuple[Statement, ...] = ()
    traps: tuple[Trap, ...] = ()
    outcomes: tuple[GapOutcome, ...]


_BOOL = "tag:yaml.org,2002:bool"


class _Loader(yaml.SafeLoader):
    """SafeLoader with only true/false as booleans; YAML 1.1 would turn a bare yes/no stance into a bool."""

    yaml_implicit_resolvers = {
        first: [(tag, rx) for tag, rx in rules if tag != _BOOL]
        for first, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


_Loader.add_implicit_resolver(_BOOL, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_yaml_raw(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)


def load_yaml[M: BaseModel](path: Path, model: type[M]) -> M:
    return model.model_validate(load_yaml_raw(path))


def dump_yaml(obj: BaseModel | dict[str, Any], path: Path) -> None:
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=120), encoding="utf-8")
