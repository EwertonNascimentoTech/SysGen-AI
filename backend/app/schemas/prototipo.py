from datetime import datetime

from pydantic import BaseModel, Field


class PrototipoPromptOut(BaseModel):
    prompt: str = Field(..., description="Prompt gerado para protótipo UX/UI a partir do PRD.")
    prd_version: int | None = Field(None, description="Versão do PRD utilizada na geração.")
    prompt_version: int = Field(..., description="Versão guardada na base (histórico).")
    finish_reason: str | None = None


class StitchLatestOut(BaseModel):
    """Último ecrã Stitch (API) guardado para o projeto."""

    stitch_project_id: str
    screen_id: str
    html_url: str
    image_url: str
    created_at: datetime | None = None
    saved_id: int | None = Field(None, description="Chave da linha em project_stitch_generations.")
    approved_at: datetime | None = None
    approved_by_email: str | None = None
    export_storage_prefix: str | None = Field(
        None,
        description="Prefixo MinIO: prototipo/<nome_projeto>/<id>/ (só ecrãs).",
    )


class PrototipoDocumentOut(BaseModel):
    """Última versão do prompt de protótipo (espelho em `projects`)."""

    prompt: str
    version: int | None = None
    saved_at: datetime | None = None
    prd_version_used: int | None = None
    stitch_latest: StitchLatestOut | None = None


class PrototipoVersionItemOut(BaseModel):
    version: int
    created_at: datetime
    created_by_email: str | None = None
    is_latest: bool = False


class PrototipoVersionDetailOut(BaseModel):
    version: int
    prompt: str
    prd_version_used: int | None = None
    created_at: datetime
    created_by_email: str | None = None
    is_latest: bool = False


class PrototipoPromptSaveBody(BaseModel):
    prompt: str = Field(..., min_length=1, description="Texto do prompt (nova versão ao guardar a partir da última).")


class StitchApiStatusOut(BaseModel):
    """Disponibilidade do runner Node + STITCH_API_KEY (API MCP, não o site web)."""

    ready: bool
    detail: str = ""


class StitchApiGenerateOut(BaseModel):
    stitch_project_id: str
    screen_id: str
    html_url: str
    image_url: str
    saved_id: int | None = Field(None, description="Registo gravado em project_stitch_generations.")


class StitchApproveExportOut(BaseModel):
    """Resposta após aprovar e gravar só os ecrãs no MinIO (pastas por título da página)."""

    storage_prefix: str = Field(..., description="Prefixo no bucket, ex.: prototipo/Meu_Projeto/12/.")


class StitchExportManifestOut(BaseModel):
    """Lista de caminhos relativos ao prefixo para descarregar a pasta (sem ZIP) via API."""

    storage_prefix: str
    files: list[str] = Field(default_factory=list, description="Caminhos relativos, ex.: Titulo_ecra/meta.json")
