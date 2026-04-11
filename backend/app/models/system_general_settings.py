from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemGeneralSettings(Base):
    """Uma única linha (id=1) com parâmetros gerais editáveis na UI de Configurações."""

    __tablename__ = "system_general_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_name: Mapped[str] = mapped_column(String(255), default="Sovereign Enterprise AI")
    locale: Mapped[str] = mapped_column(String(32), default="pt-BR")
    audit_strict: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_indexing: Mapped[bool] = mapped_column(Boolean, default=False)
