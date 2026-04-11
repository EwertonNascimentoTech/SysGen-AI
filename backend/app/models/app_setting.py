from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Chave estável para PAT de serviço GitHub guardado na base (fallback após OAuth do utilizador).
GITHUB_SERVICE_TOKEN_KEY = "github_service_token"


class AppSetting(Base):
    """Pares chave → valor encriptado para segredos de sistema (ex.: PAT GitHub)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_encrypted: Mapped[str] = mapped_column(Text)
    """Últimos caracteres do segredo em claro (só para indicador na UI, não é o token)."""
    hint_suffix: Mapped[str | None] = mapped_column(String(8), nullable=True)
