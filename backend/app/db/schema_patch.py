"""Patches de esquema leves (sem Alembic) para colunas adicionadas após a criação inicial."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def apply_project_prd_schema(sync_conn: Connection) -> None:
    """Colunas PRD em `projects` + tabela `project_prd_versions` (bases criadas antes destes campos)."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        try:
            r = sync_conn.execute(text('PRAGMA table_info("projects")'))
            existing = {row[1] for row in r}
        except Exception:
            return
        if "prd_markdown" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prd_markdown TEXT"))
        if "prd_markdown_saved_at" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prd_markdown_saved_at DATETIME"))
        if "prd_current_version" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prd_current_version INTEGER"))
        cur = sync_conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_prd_versions'"
            )
        )
        if cur.fetchone() is None:
            sync_conn.execute(
                text(
                    """
                    CREATE TABLE project_prd_versions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        version INTEGER NOT NULL,
                        markdown TEXT NOT NULL,
                        created_at DATETIME DEFAULT (datetime('now')),
                        created_by_email VARCHAR(255),
                        CONSTRAINT fk_project_prd_versions_project FOREIGN KEY(project_id)
                            REFERENCES projects (id) ON DELETE CASCADE,
                        CONSTRAINT uq_project_prd_versions_project_version UNIQUE (project_id, version)
                    )
                    """
                )
            )
            sync_conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_project_prd_versions_project_id "
                    "ON project_prd_versions (project_id)"
                )
            )
        return

    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prd_markdown TEXT"))
    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prd_markdown_saved_at TIMESTAMPTZ"))
    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prd_current_version INTEGER"))
    # Tabela de versões: create_all já cobre instalações novas; para Postgres antigo sem tabela,
    # o utilizador pode correr migração manual. Evita DDL complexo condicional aqui.


def apply_project_prototipo_schema(sync_conn: Connection) -> None:
    """Colunas de prompt de protótipo em `projects` + tabela `project_prototipo_prompt_versions`."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        try:
            r = sync_conn.execute(text('PRAGMA table_info("projects")'))
            existing = {row[1] for row in r}
        except Exception:
            return
        if "prototipo_prompt" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prototipo_prompt TEXT"))
        if "prototipo_prompt_saved_at" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prototipo_prompt_saved_at DATETIME"))
        if "prototipo_current_version" not in existing:
            sync_conn.execute(text("ALTER TABLE projects ADD COLUMN prototipo_current_version INTEGER"))
        cur = sync_conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_prototipo_prompt_versions'"
            )
        )
        if cur.fetchone() is None:
            sync_conn.execute(
                text(
                    """
                    CREATE TABLE project_prototipo_prompt_versions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        version INTEGER NOT NULL,
                        prompt TEXT NOT NULL,
                        prd_version_used INTEGER,
                        created_at DATETIME DEFAULT (datetime('now')),
                        created_by_email VARCHAR(255),
                        CONSTRAINT fk_project_prototipo_prompt_versions_project FOREIGN KEY(project_id)
                            REFERENCES projects (id) ON DELETE CASCADE,
                        CONSTRAINT uq_project_prototipo_prompt_versions_project_version UNIQUE (project_id, version)
                    )
                    """
                )
            )
            sync_conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_project_prototipo_prompt_versions_project_id "
                    "ON project_prototipo_prompt_versions (project_id)"
                )
            )
        return

    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prototipo_prompt TEXT"))
    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prototipo_prompt_saved_at TIMESTAMPTZ"))
    sync_conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS prototipo_current_version INTEGER"))
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS project_prototipo_prompt_versions (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                prd_version_used INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                created_by_email VARCHAR(255),
                CONSTRAINT uq_project_prototipo_prompt_versions_project_version UNIQUE (project_id, version)
            )
            """
        )
    )
    sync_conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_project_prototipo_prompt_versions_project_id "
            "ON project_prototipo_prompt_versions (project_id)"
        )
    )


def apply_project_stitch_generation_schema(sync_conn: Connection) -> None:
    """Tabela `project_stitch_generations` (histórico de ecrãs gerados via API Stitch)."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        cur = sync_conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_stitch_generations'"
            )
        )
        if cur.fetchone() is None:
            sync_conn.execute(
                text(
                    """
                    CREATE TABLE project_stitch_generations (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        stitch_project_id VARCHAR(64) NOT NULL,
                        screen_id VARCHAR(128) NOT NULL,
                        html_url TEXT NOT NULL,
                        image_url TEXT NOT NULL,
                        created_at DATETIME DEFAULT (datetime('now')),
                        created_by_email VARCHAR(255),
                        approved_at DATETIME,
                        approved_by_email VARCHAR(255),
                        export_storage_prefix VARCHAR(512),
                        CONSTRAINT fk_project_stitch_generations_project FOREIGN KEY(project_id)
                            REFERENCES projects (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            sync_conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_project_stitch_generations_project_id "
                    "ON project_stitch_generations (project_id)"
                )
            )
        return

    # Postgres
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS project_stitch_generations (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                stitch_project_id VARCHAR(64) NOT NULL,
                screen_id VARCHAR(128) NOT NULL,
                html_url TEXT NOT NULL,
                image_url TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                created_by_email VARCHAR(255),
                approved_at TIMESTAMPTZ,
                approved_by_email VARCHAR(255),
                export_storage_prefix VARCHAR(512)
            )
            """
        )
    )
    sync_conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_project_stitch_generations_project_id "
            "ON project_stitch_generations (project_id)"
        )
    )


def apply_project_stitch_generations_approval_columns(sync_conn: Connection) -> None:
    """Colunas approved_at / approved_by_email em bases criadas antes destes campos."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        try:
            r = sync_conn.execute(text('PRAGMA table_info("project_stitch_generations")'))
            existing = {row[1] for row in r}
        except Exception:
            return
        if not existing:
            return
        if "approved_at" not in existing:
            sync_conn.execute(text("ALTER TABLE project_stitch_generations ADD COLUMN approved_at DATETIME"))
        if "approved_by_email" not in existing:
            sync_conn.execute(text("ALTER TABLE project_stitch_generations ADD COLUMN approved_by_email VARCHAR(255)"))
        return
    sync_conn.execute(
        text(
            "ALTER TABLE project_stitch_generations ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ"
        )
    )
    sync_conn.execute(
        text(
            "ALTER TABLE project_stitch_generations ADD COLUMN IF NOT EXISTS approved_by_email VARCHAR(255)"
        )
    )


def apply_project_stitch_export_storage_prefix_column(sync_conn: Connection) -> None:
    """Coluna export_storage_prefix (prefixo MinIO/S3 do último pacote aprovado)."""
    dialect = sync_conn.engine.dialect.name
    if dialect == "sqlite":
        try:
            r = sync_conn.execute(text('PRAGMA table_info("project_stitch_generations")'))
            existing = {row[1] for row in r}
        except Exception:
            return
        if not existing:
            return
        if "export_storage_prefix" not in existing:
            sync_conn.execute(
                text("ALTER TABLE project_stitch_generations ADD COLUMN export_storage_prefix VARCHAR(512)")
            )
        return
    sync_conn.execute(
        text(
            "ALTER TABLE project_stitch_generations ADD COLUMN IF NOT EXISTS export_storage_prefix VARCHAR(512)"
        )
    )


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
