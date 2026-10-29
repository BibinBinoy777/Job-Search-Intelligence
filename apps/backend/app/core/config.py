from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, TypeAdapter, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env", extra="ignore"
    )
    database_url: str = "postgresql+psycopg://localhost/job_search"
    app_env: Literal["development", "test", "production"] = "development"
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cookie_secure: bool = False
    allow_registration: bool = True
    session_hours: int = 12
    himalayas_api_key: SecretStr | None = None
    ingestion_timeout_seconds: float = Field(default=10, ge=1, le=30)
    ingestion_max_bytes: int = Field(default=3000000, ge=1000, le=10000000)
    ingestion_attempts: int = Field(default=3, ge=1, le=4)
    automation_enabled: bool = True
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_sender: str | None = None
    app_base_url: str = "http://127.0.0.1:5173"
    resume_storage_root: Path = Path.home() / ".job-search-intelligence" / "private-resumes"
    resume_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    resume_quota_bytes: int = Field(default=50 * 1024 * 1024, ge=1024, le=500 * 1024 * 1024)
    resume_parser_timeout_seconds: float = Field(default=15, ge=1, le=30)
    resume_max_pages: int = Field(default=50, ge=1, le=100)
    resume_max_text_chars: int = Field(default=120000, ge=1000, le=250000)
    resume_max_sections: int = Field(default=1500, ge=10, le=3000)

    @model_validator(mode="after")
    def validate_deployment(self):
        from urllib.parse import urlsplit

        base = urlsplit(self.app_base_url)
        if (
            base.scheme not in {"http", "https"}
            or not base.hostname
            or base.username
            or base.password
            or base.query
            or base.fragment
            or base.path not in {"", "/"}
        ):
            raise ValueError(
                "APP_BASE_URL must be an HTTP(S) origin without credentials, query or path"
            )
        if self.smtp_sender:
            TypeAdapter(EmailStr).validate_python(self.smtp_sender)
        if self.app_env == "production" and self.smtp_host and base.scheme != "https":
            raise ValueError("Production email requires an HTTPS APP_BASE_URL")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("A PostgreSQL psycopg DATABASE_URL is required")
        if not 1 <= self.session_hours <= 48:
            raise ValueError("SESSION_HOURS must be between 1 and 48")
        if self.app_env == "production":
            if (
                not self.cookie_secure
                or not self.allowed_origins
                or any(not x.startswith("https://") or "*" in x for x in self.allowed_origins)
            ):
                raise ValueError("Production requires secure cookies and explicit HTTPS origins")
            if "@" not in self.database_url or "<" in self.database_url:
                raise ValueError("Production requires configured PostgreSQL credentials")
        return self


settings = Settings()
