from fastapi import FastAPI

from app import __version__
from app.api import internal, workspace

app = FastAPI(
    title="VART", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
)
app.include_router(workspace.router)
app.include_router(internal.router)
