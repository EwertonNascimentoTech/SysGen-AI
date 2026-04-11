"""Patches de esquema leves (sem Alembic) para colunas adicionadas após a criação inicial."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def apply_kanban_template_metadata_columns(sync_conn: Connection) -> None:
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        r = sync_conn.execute(text("PRAGMA table_info(kanban_templates)"))
        existing = {row[1] for row in r}
        if "description" not in existing:
            sync_conn.execute(text("ALTER TABLE kanban_templates ADD COLUMN description TEXT"))
        if "methodology" not in existing:
            sync_conn.execute(text("ALTER TABLE kanban_templates ADD COLUMN methodology VARCHAR(128)"))
        return
    sync_conn.execute(text("ALTER TABLE kanban_templates ADD COLUMN IF NOT EXISTS description TEXT"))
    sync_conn.execute(text("ALTER TABLE kanban_templates ADD COLUMN IF NOT EXISTS methodology VARCHAR(128)"))


def apply_governance_advance_rule_on_violation(sync_conn: Connection) -> None:
    """Adiciona on_violation ao catálogo de regras (instalações já existentes)."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        try:
            r = sync_conn.execute(text("PRAGMA table_info(governance_advance_rules)"))
            existing = {row[1] for row in r}
        except Exception:
            return
        if "on_violation" not in existing:
            sync_conn.execute(
                text(
                    "ALTER TABLE governance_advance_rules ADD COLUMN on_violation VARCHAR(32) NOT NULL DEFAULT 'bloqueio'"
                )
            )
        return
    sync_conn.execute(
        text(
            "ALTER TABLE governance_advance_rules ADD COLUMN IF NOT EXISTS on_violation VARCHAR(32) NOT NULL DEFAULT 'bloqueio'"
        )
    )
