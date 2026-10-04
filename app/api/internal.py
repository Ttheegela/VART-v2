import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import SessionDep
from app.services.workspaces import cleanup_expired
from app.settings import get_settings

router = APIRouter(include_in_schema=False)


def require_cron(authorization: Annotated[str | None, Header()] = None) -> None:
    # Vercel cron sends "Authorization: Bearer $CRON_SECRET"; no secret configured = closed.
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest((authorization or "").encode(), f"Bearer {secret}".encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


CronDep = Annotated[None, Depends(require_cron)]


@router.get("/api/internal/cleanup")
def cleanup(_: CronDep, session: SessionDep) -> dict[str, int]:
    return cleanup_expired(session)
