from typing import Literal

from pydantic import BaseModel, Field


class CursorArtifactCreate(BaseModel):
    kind: str = Field(pattern="^(rule|skill|mcp)$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    content: str | None = None
    status: Literal["ativo", "inativo"] = "inativo"


class CursorArtifactPatch(BaseModel):
    kind: str | None = Field(default=None, pattern="^(rule|skill|mcp)$")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    content: str | None = None
    status: Literal["ativo", "inativo"] | None = None


class CursorArtifactOut(BaseModel):
    id: int
    kind: str
    name: str
    description: str | None
    content: str | None = None
    status: str
    linked_projects_count: int = 0

    class Config:
        from_attributes = True


class LinkArtifactBody(BaseModel):
    artifact_id: int
