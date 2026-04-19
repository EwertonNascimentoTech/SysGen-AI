from datetime import date

from pydantic import BaseModel, Field


class ProjectTaskOut(BaseModel):
    id: int
    project_id: int
    title: str
    bloco_tag: str | None = None
    description: str | None
    entrega_resumo: str | None = None
    column_key: str
    priority: str
    assignee: str | None
    due_date: date | None
    governance_aligned: bool
    position: int

    class Config:
        from_attributes = True


class ProjectTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    bloco_tag: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=8000)
    entrega_resumo: str | None = Field(None, max_length=16000)
    column_key: str = Field(default="todo", pattern=r"^[a-z0-9_]{1,64}$")
    priority: str = Field(default="medium", pattern="^(high|medium|low)$")
    assignee: str | None = Field(None, max_length=255)
    due_date: date | None = None
    governance_aligned: bool = False


class ProjectTaskReorderBody(BaseModel):
    """Ordem completa das tarefas numa raia (IDs devem coincidir exactamente com as tarefas dessa coluna)."""

    column_key: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    task_ids: list[int] = Field(min_length=0)


class ProjectTaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=512)
    bloco_tag: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=8000)
    entrega_resumo: str | None = Field(None, max_length=16000)
    column_key: str | None = Field(None, pattern=r"^[a-z0-9_]{1,64}$")
    priority: str | None = Field(None, pattern="^(high|medium|low)$")
    assignee: str | None = Field(None, max_length=255)
    due_date: date | None = None
    governance_aligned: bool | None = None
    position: int | None = None
