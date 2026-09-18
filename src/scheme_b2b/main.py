from secrets import compare_digest

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .airtable import AirtableClient
from .config import get_settings
from .fns_index import FNSIndex
from .service import SearchService
from .sources import build_sources


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
    if not build_sources(settings):
        missing.append("SEARCH_SOURCE")
    mode = settings.fns_mode.lower()
    if settings.require_fns_confirmation:
        if mode == "checksum":
            missing.append("FNS_OFFICIAL_VERIFICATION")
        elif mode == "official" and not settings.fns_verify_url:
            missing.append("FNS_VERIFY_URL")
        elif mode == "bulk" and not settings.fns_egrul_bulk_path:
            missing.append("FNS_EGRUL_BULK_PATH")
        elif mode == "bulk-index":
            try:
                if not FNSIndex(settings.fns_index_db_url).is_fresh(
                    settings.fns_index_max_age_hours
                ):
                    missing.append("FNS_INDEX_FRESHNESS")
            except Exception:
                missing.append("FNS_INDEX")
        elif mode not in {"official", "bulk", "bulk-index"}:
            missing.append("FNS_MODE")
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
