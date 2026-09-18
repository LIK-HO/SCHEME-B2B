from secrets import compare_digest

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .airtable import AirtableClient
from .config import get_settings
from .fns import FNSVerifier
from .service import SearchService
from .sources import source_configuration_errors


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


def _authorize(x_api_key: str | None) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API_KEY is not configured")
    if not x_api_key or not compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


class RunRequest(BaseModel):
    manual: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
def ready() -> dict[str, str]:
    missing: list[str] = []
    if not settings.airtable_token:
        missing.append("AIRTABLE_TOKEN")
    if not settings.api_key:
        missing.append("API_KEY")
    missing.extend(source_configuration_errors(settings))
    fns_error = FNSVerifier(settings).readiness_error()
    if fns_error:
        missing.append(fns_error)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Not ready: {', '.join(missing)}",
        )
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
