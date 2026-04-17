from datetime import date, datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    product_owner: str
    directory_id: int
    methodology: str = Field(pattern="^(base44|prd)$")
    planned_start: date
    planned_end: date
    template_id: int


class ProjectPatch(BaseModel):
    """Atualização parcial dos dados cadastrais do processo (sem trocar template Kanban)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    product_owner: str | None = Field(None, min_length=1, max_length=255)
    directory_id: int | None = None
    methodology: str | None = Field(None, pattern="^(base44|prd)$")
    planned_start: date | None = None
    planned_end: date | None = None
    ended_at: date | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    product_owner: str
    directory_id: int
    directory_name: str | None = None
    methodology: str
    planned_start: date
    planned_end: date
    ended_at: date | None
    template_id: int
    current_column_id: int
    current_column_title: str | None = None
    github_repo_url: str | None
    github_tag: str | None
    prd_markdown_saved_at: datetime | None = None
    prd_current_version: int | None = None
    prototipo_prompt_saved_at: datetime | None = None
    prototipo_current_version: int | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ProjectFilter(BaseModel):
    name: str | None = None
    directory_id: int | None = None
    product_owner: str | None = None
    methodology: str | None = None
    current_column_id: int | None = None
    planned_start_from: date | None = None
    planned_start_to: date | None = None
    planned_end_from: date | None = None
    planned_end_to: date | None = None
    ended_from: date | None = None
    ended_to: date | None = None


class MoveKanbanBody(BaseModel):
    target_column_id: int


class GovernanceNotice(BaseModel):
    """Mensagem de governança com link opcional para corrigir no detalhe do projeto."""

    message: str
    href: str | None = None


class KanbanMoveOut(BaseModel):
    project: ProjectOut
    governance_warnings: list[GovernanceNotice] = []


class GitHubLinkBody(BaseModel):
    repo_url: str


class TagSelectBody(BaseModel):
    tag: str
