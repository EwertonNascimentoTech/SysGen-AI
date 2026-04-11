from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernanceAdvanceRule(Base):
    """Catálogo de regras de avanço (referenciadas pelas fases do Kanban via rules_json.applied_rule_ids)."""

    __tablename__ = "governance_advance_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_key: Mapped[str] = mapped_column(String(64))
    min_tags_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: bloqueio = impede avanço; alerta = avanço permitido, mensagem devolvida em governance_warnings
    on_violation: Mapped[str] = mapped_column(String(32), default="bloqueio")
