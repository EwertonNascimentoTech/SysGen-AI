from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlanejamentoContextOut(BaseModel):
    """Stack e sinais de configuração do ambiente (sem segredos) para a UI de planejamento."""

    stack_documentada: str = Field(
        description="Stack de referência da plataforma alinhada ao agente de planejamento.",
    )
    methodology: str = Field(description="Metodologia do projecto (ex.: prd, base44).")
    github_repo_url: str | None = None
    github_tag: str | None = None
    s3_configured: bool = Field(False, description="MinIO/S3 configurado no servidor.")
    github_oauth_configured: bool = Field(False, description="OAuth GitHub (client id + secret) no servidor.")
    stitch_api_configured: bool = Field(False, description="STITCH_API_KEY definida no servidor.")
    azure_planejador_ready: bool = Field(
        False,
        description="Azure AI Agents com endpoint e AZURE_AI_AGENT_PLANEJADOR_ID prontos.",
    )


class PlanejamentoStoredOut(BaseModel):
    """JSON de planejamento persistido no projeto (não incluído em listagens para evitar payload grande)."""

    text: str | None = Field(None, description="Corpo JSON (string) ou null se ainda não gerado")
    saved_at: datetime | None = None
    approved_at: datetime | None = None
    context: PlanejamentoContextOut = Field(
        description="Stack e ambiente (sempre preenchido para a listagem na aba Planejamento).",
    )


class PlanejamentoApprovalBody(BaseModel):
    approved: bool = True


class PlanejamentoApprovalOut(BaseModel):
    approved_at: datetime | None = None
    tasks_removed: int = Field(0, description="Tarefas do quadro removidas (geradas por planejamentos anteriores).")
    tasks_created: int = Field(0, description="Novas tarefas criadas na primeira raia ao aprovar.")


class PlanejamentoAgentOut(BaseModel):
    text: str = Field(description="Resposta do agente (JSON ou texto)")
    finish_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
