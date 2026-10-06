"""Questionnaires: import, the column mapper, samples (spec 5 step 2, 6.10). Owner: lane 3A-inputs (Task 5);
POST .../runs belongs to lane 3A-runs and lives in app/api/runs.py."""

import uuid

from fastapi import APIRouter, Request, UploadFile

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS, Mapping, QuestionnaireDetail, QuestionnaireOut

router = APIRouter(tags=["questionnaires"], responses=ERRORS)


@router.get("/api/questionnaires")
def list_questionnaires(ws: WorkspaceDep, session: SessionDep) -> list[QuestionnaireOut]:
    """Every questionnaire in the workspace, newest first (a built-in `csf` one included, Plan 6B)."""
    raise not_built()


@router.post("/api/questionnaires", status_code=201)
def upload_questionnaire(
    ws: WorkspaceDep, session: SessionDep, request: Request, file: UploadFile
) -> QuestionnaireOut:
    """Multipart xlsx or csv. Answers the detected mapping and a preview; no items exist until the visitor
    confirms with PUT .../mapping. 422 for a refused file; 429 per network (`upload`)."""
    raise not_built()


@router.post("/api/questionnaires/sample/{name}", status_code=201)
def load_sample_questionnaire(name: str, ws: WorkspaceDep, session: SessionDep) -> QuestionnaireDetail:
    """`vsq-a` (xlsx) or `mvsp-b` (csv), mapped and itemised at once. 404 for another name."""
    raise not_built()


@router.put("/api/questionnaires/{questionnaire_id}/mapping")
def confirm_mapping(
    questionnaire_id: uuid.UUID, mapping: Mapping, ws: WorkspaceDep, session: SessionDep
) -> QuestionnaireDetail:
    """Replace the items with the ones this mapping reads. 422 when it finds none or more than 150; 409 once a
    run exists for the questionnaire."""
    raise not_built()


@router.get("/api/questionnaires/{questionnaire_id}")
def get_questionnaire(
    questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep
) -> QuestionnaireDetail:
    raise not_built()
