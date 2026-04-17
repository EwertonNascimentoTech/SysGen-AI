from __future__ import annotations

import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pasta que contém o pacote Python `app` (em dev: …/plataforma-governanca-ia/backend; no Docker: /app)
_APP_TREE_ROOT = Path(__file__).resolve().parents[2]


def _dotenv_file_paths() -> tuple[Path, ...]:
    """
    Ficheiros .env a carregar (ordem: primeiro a raiz do monorepo, depois a pasta do backend).
    No Docker (WORKDIR /app) só entra /app/.env — nunca a raiz do sistema.
    """
    paths: list[Path] = []
    parent = _APP_TREE_ROOT.parent
    try:
        if (parent / "backend").resolve() == _APP_TREE_ROOT.resolve():
            paths.append(parent / ".env")
    except (OSError, ValueError):
        pass
    paths.append(_APP_TREE_ROOT / ".env")
    return tuple(paths)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_dotenv_file_paths(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Plataforma Governança IA"
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    # Aceita sqlite+aiosqlite ou postgresql+asyncpg (ou postgres:// normalizado em session)
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    # str | list: env com vírgulas não pode ser list[str] puro — pydantic-settings faria json.loads e falharia
    cors_origins: str | list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # GitHub OAuth (RF-17)
    github_client_id: str = ""
    github_client_secret: str = ""
    # URL absoluta registrada no app OAuth GitHub (ex.: http://127.0.0.1:8000/api/auth/github/callback)
    github_oauth_callback_url: str = "http://127.0.0.1:8000/api/auth/github/callback"

    # Frontend: redirecionamento pós-login GitHub (ex.: http://localhost:5173/auth/callback)
    frontend_oauth_redirect_base: str = "http://localhost:5173/auth/callback"

    redis_url: str = "redis://127.0.0.1:6379/0"

    # MinIO / S3 compatível (RF anexos / storage)
    s3_endpoint_url: str | None = None  # ex. http://minio:9000 (rede Docker)
    # URL pública para o browser em presigned URLs (ex. http://localhost:9000)
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "governanca"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_presigned_ttl_seconds: int = 3600

    # Azure OpenAI (chat PRD / entrevista)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # Azure AI Agents / Foundry (prioridade sobre OpenAI REST quando endpoint + agent_id definidos)
    azure_ai_project_endpoint: str = ""
    azure_ai_project_connection_string: str = ""
    azure_ai_agent_id: str = ""
    # Agente dedicado à geração de prompt de protótipo (UX/UI) a partir do PRD.
    azure_ai_agent_prototipo_id: str = ""
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # Google Stitch API (@google/stitch-sdk / MCP stitch.googleapis.com) — opcional; ver backend/stitch_runner/
    stitch_api_key: str = ""
    stitch_project_id: str = ""

    @field_validator("azure_openai_endpoint", "azure_ai_project_endpoint", mode="before")
    @classmethod
    def strip_azure_endpoint(cls, v):
        if v is None:
            return ""
        return str(v).strip().rstrip("/")

    @field_validator("github_client_id", "github_client_secret", mode="before")
    @classmethod
    def strip_github_oauth(cls, v):
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("github_oauth_callback_url", "frontend_oauth_redirect_base", mode="before")
    @classmethod
    def normalize_oauth_urls(cls, v):
        """GitHub exige redirect_uri idêntico ao registo — sem barra final nem espaços."""
        if v is None:
            return ""
        s = str(v).strip().rstrip("/")
        return s

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in s.split(",") if part.strip()]
        return v


settings = Settings()
