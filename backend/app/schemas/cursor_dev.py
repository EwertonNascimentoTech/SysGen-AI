from __future__ import annotations

from pydantic import BaseModel, Field


class CursorDevPollOut(BaseModel):
    """Estado para o modo automático (polling) do «Desenvolver»."""

    can_start: bool = Field(..., description="True se pode chamar POST cursor-dev/start neste momento")
    has_active_agent: bool = Field(..., description="Há run em CREATING ou RUNNING (após sincronizar com a Cursor)")
    backlog_tasks: int = Field(0, ge=0, description="Tarefas na primeira coluna do quadro")
    reason: str | None = Field(
        None,
        description="Código curto quando can_start é false (ex.: BUSY, NO_TASKS, EMPTY_REPO)",
    )


class CursorDevStartOut(BaseModel):
    task_id: int = Field(..., description="Tarefa movida para Em execução e enviada ao agente")
    cursor_agent_id: str
    agent_status: str = Field(..., description="Estado inicial devolvido pela Cursor API")
    repo_initialized: bool = Field(
        default=False,
        description="True se o repositório estava vazio e foi criado README.md via API GitHub",
    )
    integration_branch: str | None = Field(
        default=None,
        description="Branch fixo na Cursor quando o arranque foi com auto=1 (modo fila num só branch)",
    )
