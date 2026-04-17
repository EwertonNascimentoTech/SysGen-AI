from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PrdMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=100_000)


class PrdAttachmentIn(BaseModel):
    filename: str = Field(max_length=512)
    mime_type: str = Field(max_length=128)
    content_base64: str = Field(max_length=12_000_000)


class PrdChatRequest(BaseModel):
    """Histórico da conversa; a última mensagem deve ser do utilizador. Anexos aplicam-se a essa mensagem."""

    messages: list[PrdMessageIn] = Field(min_length=1)
    mode: Literal["chat", "interview"] = "interview"
    attachments: list[PrdAttachmentIn] = Field(default_factory=list)


class PrdChatResponse(BaseModel):
    message: str
    finish_reason: str | None = None
    prd_save_recommended: bool = Field(
        default=False,
        description="Resposta identificada como documento PRD; o cliente pode mostrar «Salvar».",
    )


class PrdMarkdownSaveBody(BaseModel):
    markdown: str = Field(default="", max_length=500_000)


class PrdMarkdownDocumentOut(BaseModel):
    markdown: str | None = None
    saved_at: datetime | None = None
    version: int | None = None


class PrdAzureStatusOut(BaseModel):
    configured: bool


class PrdVersionItemOut(BaseModel):
    version: int
    created_at: datetime | None = None
    created_by_email: str | None = None
    is_latest: bool = False


class PrdVersionDetailOut(BaseModel):
    version: int
    markdown: str
    created_at: datetime | None = None
    created_by_email: str | None = None
    is_latest: bool = False
