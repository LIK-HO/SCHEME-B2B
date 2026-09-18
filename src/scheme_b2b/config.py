from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SCHEME-B2B"
    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str = ""

    airtable_base_id: str = "appI8LyuBMv5z468N"
    airtable_token: str = ""
    airtable_timeout_seconds: float = 30

    airtable_table_companies: str = "tbld836qMgcqhTB0M"
    airtable_table_clients: str = "tbldiqR1TDB4PM7Ds"
    airtable_table_archive: str = "tblq2wCGQ4ih3vsB8"
    airtable_table_search: str = "tblNgRcnSv60i076B"
    airtable_table_sources: str = "tblaOy36JLTnoQXhN"
    airtable_table_notifications: str = "tblPPasf6bpmGFZcw"

    search_profile_name: str = "Москва B2B — базовый"
    source_json_file: str = ""
    source_json_url: str = ""
    fns_rsmp_path: str = ""
    fns_egrul_bulk_path: str = ""
    rosstat_registry_path: str = ""
    source_timeout_seconds: float = 30

    fns_mode: str = "checksum"
    fns_verify_url: str = ""
    fns_verify_token: str = ""
    require_fns_confirmation: bool = True

    max_enabled: bool = False
    max_bot_token: str = ""
    max_recipient_id: str = ""
    max_api_base: str = "https://platform-api2.max.ru"
    max_timeout_seconds: float = 20

    email_enabled: bool = False
    email_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    outbox_max_attempts: int = 5
    outbox_backoff_base_seconds: int = 10

    local_db_url: str = Field(default="sqlite:///data/scheme_b2b.sqlite3")
    fns_index_db_url: str = Field(default="sqlite:///data/fns_index.sqlite3")
    fns_index_max_age_hours: float = Field(default=48, gt=0)

    outbox_lease_seconds: int = Field(default=600, gt=0)
    outbox_jitter_ratio: float = Field(default=0.2, ge=0, le=1)

    max_candidates_per_source: int = Field(default=2000, gt=0)
    max_new_records_per_run: int = Field(default=100, gt=0)

    @property
    def local_db_path(self) -> Path | None:
        if not self.local_db_url.startswith("sqlite:///"):
            return None
        return Path(self.local_db_url.removeprefix("sqlite:///"))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.local_db_path:
        settings.local_db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
