"""Export (spec 5 step 7, 6.10). Owner: lane 3A-inputs (Task 6)."""

import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import Conflict, NotFound, limit
from app.api.gap import gap_sheet, latest_gap
from app.api.schemas import ERRORS, Mapping
from app.db.models import Questionnaire, Run
from app.export import NOTICE, export_csv, export_xlsx, gap_report, rows_for
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
    response is an attachment with an ASCII-safe file name. A gap-check run answers the gap-report workbook
    instead (CSF spec 7), 409 while it is running. An xlsx questionnaire's export also carries the
    workspace's latest done gap check as a `Gap report` sheet (renamed `Gap report (2)` and so on if the file
    has one), stating its scope and run date; a csv is unchanged. 429 per network (`export`, 60 an hour)."""
    limit(request, session, "export")
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ws.id))
    if run is None:
        raise NotFound()
    q = session.get_one(Questionnaire, run.questionnaire_id)
    if q.source == "csf":
        # re-opened rows would read "Not run yet" under the old date (adversary-2 M3)
        if run.status != "done":
            raise Conflict("The check is running; export when it is done.")
        return _gap_report(session, ws.id, run, q)
    confirmed = (q.mapping or {}).get("confirmed")
    if not q.original_bytes or not confirmed:
        raise Conflict("This questionnaire has no file to write into.")
    mapping, rows = Mapping(**confirmed), rows_for(session, run.id)
    is_csv = q.filename.lower().endswith(".csv")
    found = None if is_csv else latest_gap(session, ws.id)
    gap = gap_sheet(session, *found) if found else None
    body = (
        export_csv(q.original_bytes, mapping, rows)
        if is_csv
        else export_xlsx(q.original_bytes, mapping, rows, gap)
    )
    audit_log.record(
        session,
        ws.id,
        "export",
        ref=str(run.id),
        detail={"rows": len(rows), "gap": gap.scope if gap else None},
    )
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


def _gap_report(session: SessionDep, ws_id: uuid.UUID, run: Run, q: Questionnaire) -> Response:
    """A gap-check run's export (CSF spec 7): the gap-report workbook, named by the scope (a server value)."""
    g = gap_sheet(session, q, run)
    body = gap_report(g)
    audit_log.record(
        session, ws_id, "export", ref=str(run.id), detail={"rows": len(g.rows), "scope": g.scope}
    )
    session.commit()
    return Response(
        body,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="csf-2.0-{g.scope}-gap-report.xlsx"'},
    )
