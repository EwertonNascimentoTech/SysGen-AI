from pydantic import BaseModel, Field


class CursorArtifactCreate(BaseModel):
    kind: str = Field(pattern="^(rule|skill|mcp)$")
    name: str
    description: str | None = None
    content: str | None = None


class CursorArtifactOut(BaseModel):
    id: int
    kind: str
    name: str
    description: str | None
    status: str
    linked_projects_count: int = 0

    class Config:
        from_attributes = True


class LinkArtifactBody(BaseModel):
    artifact_id: int
