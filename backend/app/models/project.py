from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    product_owner: Mapped[str] = mapped_column(String(255))
    directory_id: Mapped[int] = mapped_column(ForeignKey("directories.id"))
    methodology: Mapped[str] = mapped_column(String(32))  # base44 | prd
    planned_start: Mapped[date] = mapped_column(Date)
    planned_end: Mapped[date] = mapped_column(Date)
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("kanban_templates.id"))
    current_column_id: Mapped[int] = mapped_column(ForeignKey("kanban_template_columns.id"))
    github_repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    directory_ref: Mapped["Directory"] = relationship(back_populates="projects")
    template: Mapped["KanbanTemplate"] = relationship()
    current_column: Mapped["KanbanTemplateColumn"] = relationship()


class ProjectAttachment(Base):
    __tablename__ = "project_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    attachment_type: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProjectWiki(Base):
    __tablename__ = "project_wikis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    tag: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, ready, error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rq_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WikiDocument(Base):
    __tablename__ = "wiki_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wiki_id: Mapped[int] = mapped_column(ForeignKey("project_wikis.id"))
    path: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(255))
    markdown: Mapped[str] = mapped_column(Text)


from app.models.directory import Directory  # noqa: E402
from app.models.kanban import KanbanTemplate, KanbanTemplateColumn  # noqa: E402
