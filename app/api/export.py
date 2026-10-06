"""Export (spec 5 step 7, 6.10). Owner: lane 3A-inputs (Task 6)."""

import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import Conflict, NotFound, limit
from app.api.schemas import ERRORS, Mapping
from app.db.models import Questionnaire, Run
from app.export import NOTICE, export_csv, export_xlsx, rows_for
from app.services import audit_log

router = APIRouter(tags=["export"], responses=ERRORS)


def disposition(filename: str, ext: str) -> str:
    """An attachment header from a user's file name: the plain name is ASCII letters, digits, - _ . only; the
    real name rides in filename*= percent-encoded, so no quote, CR or LF ever reaches the header."""
    stem = filename.rsplit(".", 1)[0]
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "questionnaire"
    name = f"{safe}-filled.{ext}"
    full = f"{stem}-filled.{ext}"
    head = f'attachment; filename="{name}"'
    return head if full == name else f"{head}; filename*=UTF-8''{quote(full, safe='')}"


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/api/runs/{run_id}/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}, "text/csv": {}}, "description": "The filled file"}},
)
def export_run(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request) -> Response:
    """The original file with the answer column filled and Status, Sources and Notes columns added; csv in,
    csv out. Unapproved answers read "Draft, not approved". Every cell written is inert text: a value starting
    with =, +, -, @, tab, CR or LF gets a ' prefix in csv, and xlsx cells are written with data_type 's'. The
    response is an attachment with an ASCII-safe file name. 429 per network (`export`, 60 an hour)."""
    limit(request, session, "export")
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ws.id))
    if run is None:
        raise NotFound()
    q = session.get_one(Questionnaire, run.questionnaire_id)
    confirmed = (q.mapping or {}).get("confirmed")
    if not q.original_bytes or not confirmed:
        raise Conflict("This questionnaire has no file to write into.")
    mapping, rows = Mapping(**confirmed), rows_for(session, run.id)
    is_csv = q.filename.lower().endswith(".csv")
    body = (export_csv if is_csv else export_xlsx)(q.original_bytes, mapping, rows)
    audit_log.record(session, ws.id, "export", ref=str(run.id), detail={"rows": len(rows)})
    session.commit()
    ext = "csv" if is_csv else "xlsx"
    return Response(
        body,
        media_type="text/csv; charset=utf-8" if is_csv else XLSX,
        headers={
            "Content-Disposition": disposition(q.filename, ext),
            **({} if is_csv else {"X-Export-Notice": NOTICE}),
        },
    )
