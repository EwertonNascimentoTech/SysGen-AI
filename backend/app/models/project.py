from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    prd_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    prd_markdown_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prd_current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prototipo_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prototipo_prompt_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prototipo_current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    directory_ref: Mapped["Directory"] = relationship(back_populates="projects")
    prd_versions: Mapped[list["ProjectPrdVersion"]] = relationship(
        "ProjectPrdVersion",
        back_populates="project",
        order_by="ProjectPrdVersion.version",
        passive_deletes=True,
    )
    prototipo_prompt_versions: Mapped[list["ProjectPrototipoPromptVersion"]] = relationship(
        "ProjectPrototipoPromptVersion",
        back_populates="project",
        order_by="ProjectPrototipoPromptVersion.version",
        passive_deletes=True,
    )
    stitch_generations: Mapped[list["ProjectStitchGeneration"]] = relationship(
        "ProjectStitchGeneration",
        back_populates="project",
        passive_deletes=True,
    )
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


class ProjectPrdVersion(Base):
    """Histórico de PRDs guardados a partir do chat (versão monotónica por projeto)."""

    __tablename__ = "project_prd_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_project_prd_versions_project_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="prd_versions")


class ProjectPrototipoPromptVersion(Base):
    """Histórico de prompts de protótipo (UX/UI) gerados ou editados por versão."""

    __tablename__ = "project_prototipo_prompt_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_prototipo_prompt_versions_project_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text)
    prd_version_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="prototipo_prompt_versions")


class ProjectStitchGeneration(Base):
    """Registo de cada geração de ecrã via API Google Stitch (MCP) para o projeto."""

    __tablename__ = "project_stitch_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    stitch_project_id: Mapped[str] = mapped_column(String(64))
    screen_id: Mapped[str] = mapped_column(String(128))
    html_url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    export_storage_prefix: Mapped[str | None] = mapped_column(String(512), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="stitch_generations")


from app.models.directory import Directory  # noqa: E402
from app.models.kanban import KanbanTemplate, KanbanTemplateColumn  # noqa: E402
