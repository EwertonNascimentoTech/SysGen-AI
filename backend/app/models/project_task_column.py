from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectTaskColumn(Base):
    """Raias do sub-Kanban de tarefas por projeto (títulos, ordem e cor do estado)."""

    __tablename__ = "project_task_columns"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_project_task_columns_project_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer)
    color_hex: Mapped[str] = mapped_column(String(7), default="#64748b")
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
