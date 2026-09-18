from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///fpl_insights.db"
    fpl_api_base: str = "https://fantasy.premierleague.com/api"
    cors_origins: str = "http://localhost:4200"
    model_version: str = "team-v1+player-v1"
    http_verify_ssl: bool = True
    vaastav_base_url: str = (
        "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
    )
    fpl_core_base_url: str = (
        "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data"
    )
    datahub_epl_base: str = (
        "https://datahub.io/core/football/english-premier-league/r/season-{}.csv"
    )
    vision_api_key: str | None = None
    vision_api_base: str = "https://api.openai.com/v1"
    vision_model: str = "gpt-4o-mini"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        if not isinstance(v, str) or not v:
            return v
        url = v
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @field_validator("database_url", mode="after")
    @classmethod
    def resolve_sqlite_database_url(cls, v: str) -> str:
        prefix = "sqlite:///"
        if not v.startswith(prefix):
            return v
        db_path = v[len(prefix) :]
        if not db_path or db_path == ":memory:":
            return v
        if len(db_path) > 2 and db_path[1] == ":":
            return v
        path = Path(db_path)
        if path.is_absolute():
            return v
        return f"{prefix}{(REPO_ROOT / db_path).as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
