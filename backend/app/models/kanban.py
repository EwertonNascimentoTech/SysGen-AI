from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KanbanTemplate(Base):
    __tablename__ = "kanban_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="rascunho")  # rascunho, publicado, arquivado
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology: Mapped[str | None] = mapped_column(String(128), nullable=True)

    columns: Mapped[list["KanbanTemplateColumn"]] = relationship(
        back_populates="template", order_by="KanbanTemplateColumn.position"
    )


class KanbanTemplateColumn(Base):
    __tablename__ = "kanban_template_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("kanban_templates.id"))
    title: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer)
    rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped[KanbanTemplate] = relationship(back_populates="columns")
