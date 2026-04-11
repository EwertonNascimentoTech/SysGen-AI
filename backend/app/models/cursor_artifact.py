from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CursorArtifact(Base):
    __tablename__ = "cursor_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))  # rule, skill, mcp
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="rascunho")


class ProjectCursorArtifact(Base):
    __tablename__ = "project_cursor_artifacts"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("cursor_artifacts.id"), primary_key=True)
