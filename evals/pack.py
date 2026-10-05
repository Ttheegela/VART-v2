"""A company pack as the eval harness sees it: the fact sheet, the questionnaires' items, the answer keys, and
loading the pack's documents into a workspace in fact-sheet order (Plan 2 addendum: never by globbing)."""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.contracts import ItemInput, Spend
from app.ingest.store import ingest_document
from app.llm.client import LLMClient
from datakit.extract import text_of
from datakit.schemas import DocSpec, Facts, Key, KeyItem, Selection, load_yaml

ROOT = Path(__file__).resolve().parent.parent
QUESTIONNAIRES = ("vsq-a", "mvsp-b")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Pack:
    name: str
    facts: Facts
    selections: dict[str, Selection]
    keys: dict[str, KeyItem]  # item code -> key entry, both questionnaires

    def path(self, spec: DocSpec) -> Path:
        return ROOT / "data" / self.name / "docs" / spec.filename

    def items(self, questionnaire: str) -> list[ItemInput]:
        return [ItemInput(i.code, i.question, i.section) for i in self.selections[questionnaire].items]

    def private_strings(self) -> list[str]:
        """What redaction must remove: every person's name and every email address in the documents."""
        found = {p.name for p in self.facts.people} | {p.email for p in self.facts.people}
        for spec in self.facts.documents:
            found |= set(_EMAIL.findall(text_of(self.path(spec))))
        return sorted(found)


def load(name: str) -> Pack:
    base = ROOT / "data" / name
    selections = {
        q: load_yaml(ROOT / "data" / "questionnaires" / f"{q}.selection.yaml", Selection)
        for q in QUESTIONNAIRES
    }
    keys: dict[str, KeyItem] = {}
    for q in QUESTIONNAIRES:
        keys.update({i.code: i for i in load_yaml(base / "key" / f"{q}.yaml", Key).items})
    return Pack(name, load_yaml(base / "facts.yaml", Facts), selections, keys)


def load_documents(
    session: Session,
    workspace_id: uuid.UUID,
    pack: Pack,
    specs: list[DocSpec],
    *,
    source: Literal["sample", "upload"],
    llm: LLMClient | None,
    model: str,
    spend: Spend,
) -> dict[str, str]:
    """Ingest `specs` in the order given; returns fact-sheet document id -> documents.id."""
    ids: dict[str, str] = {}
    for spec in specs:
        doc = ingest_document(
            session,
            workspace_id,
            spec.filename,
            pack.path(spec).read_bytes(),
            source=source,
            llm=llm,
            model=model,
            spend=spend,
        )
        ids[spec.id] = str(doc.id)
    return ids
