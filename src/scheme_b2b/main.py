from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .airtable import AirtableClient
from .config import get_settings
from .service import SearchService


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


def _authorize(x_api_key: str | None) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


class RunRequest(BaseModel):
    manual: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
def ready() -> dict[str, str]:
    if not settings.airtable_token:
        raise HTTPException(status_code=503, detail="AIRTABLE_TOKEN is not configured")
    return {"status": "ready"}


@app.post("/api/v1/search/run")
def run_search(payload: RunRequest, x_api_key: str | None = Header(default=None)) -> dict[str, object]:
    _authorize(x_api_key)
    service = SearchService(settings, AirtableClient(settings))
    return service.run_once(manual=payload.manual)


@app.post("/api/v1/outbox/dispatch")
def dispatch_outbox(x_api_key: str | None = Header(default=None)) -> dict[str, int]:
    _authorize(x_api_key)
    service = SearchService(settings, AirtableClient(settings), sources=[])
    return service.dispatch_outbox()
