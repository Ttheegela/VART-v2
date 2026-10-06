"""Export (spec 5 step 7, 6.10). Owner: lane 3A-inputs (Task 6)."""

import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS

router = APIRouter(tags=["export"], responses=ERRORS)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/api/runs/{run_id}/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}, "text/csv": {}}, "description": "The filled file"}},
)
def export_run(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> Response:
    """The original file with the answer column filled and Status, Sources and Notes columns added; csv in,
    csv out. Unapproved answers read "Draft, not approved". Every cell written is inert text: a value starting
    with =, +, -, @, tab or CR gets a ' prefix in csv, and xlsx cells are written with data_type 's'."""
    raise not_built()
