"""
Atualiza schema SQLite antigo para o modelo atual (sem dropar dados).

Uso (a partir da pasta backend, onde normalmente fica dev.db):
  python scripts/migrate_sqlite.py

Ou:
  python scripts/migrate_sqlite.py --db C:\\caminho\\dev.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return {row[1] for row in cur.fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def migrate(conn: sqlite3.Connection) -> list[str]:
    log: list[str] = []

    if not _table_exists(conn, "users"):
        log.append("Nenhuma tabela 'users' — parece base vazia ou não inicializada. Suba a API uma vez ou apague o ficheiro.")
        return log

    # user_identities
    if not _table_exists(conn, "user_identities"):
        conn.execute(
            """
            CREATE TABLE user_identities (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider VARCHAR(32) NOT NULL,
                provider_user_id VARCHAR(64) NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                CONSTRAINT fk_user_identities_user FOREIGN KEY(user_id)
                    REFERENCES users (id) ON DELETE CASCADE,
                CONSTRAINT uq_identity_provider_user UNIQUE (provider, provider_user_id)
            )
            """
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS ix_user_identities_user_id ON user_identities (user_id)'
        )
        log.append("Criada tabela user_identities.")
    else:
        log.append("Tabela user_identities já existe.")

    # project_attachments
    if _table_exists(conn, "project_attachments"):
        cols = _columns(conn, "project_attachments")
        if "content_type" not in cols:
            conn.execute("ALTER TABLE project_attachments ADD COLUMN content_type VARCHAR(128)")
            log.append("Coluna project_attachments.content_type adicionada.")
        if "size_bytes" not in cols:
            conn.execute("ALTER TABLE project_attachments ADD COLUMN size_bytes INTEGER")
            log.append("Coluna project_attachments.size_bytes adicionada.")
    else:
        log.append("Aviso: project_attachments não existe.")

    # project_wikis
    if _table_exists(conn, "project_wikis"):
        cols = _columns(conn, "project_wikis")
        if "error_message" not in cols:
            conn.execute("ALTER TABLE project_wikis ADD COLUMN error_message TEXT")
            log.append("Coluna project_wikis.error_message adicionada.")
        if "rq_job_id" not in cols:
            conn.execute("ALTER TABLE project_wikis ADD COLUMN rq_job_id VARCHAR(64)")
            log.append("Coluna project_wikis.rq_job_id adicionada.")
    else:
        log.append("Aviso: project_wikis não existe.")

    # projects — PRD guardado pelo chat
    if _table_exists(conn, "projects"):
        cols = _columns(conn, "projects")
        if "prd_markdown" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prd_markdown TEXT")
            log.append("Coluna projects.prd_markdown adicionada.")
        if "prd_markdown_saved_at" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prd_markdown_saved_at DATETIME")
            log.append("Coluna projects.prd_markdown_saved_at adicionada.")
        if "prd_current_version" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prd_current_version INTEGER")
            log.append("Coluna projects.prd_current_version adicionada.")
    else:
        log.append("Aviso: projects não existe.")

    # project_prd_versions (histórico de PRD guardados pelo chat)
    if not _table_exists(conn, "project_prd_versions"):
        conn.execute(
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_project_prd_versions_project_id ON project_prd_versions (project_id)"
        )
        log.append("Criada tabela project_prd_versions.")
    else:
        log.append("Tabela project_prd_versions já existe.")

    # projects — prompt de protótipo (versões em project_prototipo_prompt_versions)
    if _table_exists(conn, "projects"):
        cols = _columns(conn, "projects")
        if "prototipo_prompt" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prototipo_prompt TEXT")
            log.append("Coluna projects.prototipo_prompt adicionada.")
        if "prototipo_prompt_saved_at" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prototipo_prompt_saved_at DATETIME")
            log.append("Coluna projects.prototipo_prompt_saved_at adicionada.")
        if "prototipo_current_version" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN prototipo_current_version INTEGER")
            log.append("Coluna projects.prototipo_current_version adicionada.")

    if not _table_exists(conn, "project_prototipo_prompt_versions"):
        conn.execute(
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_project_prototipo_prompt_versions_project_id "
            "ON project_prototipo_prompt_versions (project_id)"
        )
        log.append("Criada tabela project_prototipo_prompt_versions.")
    else:
        log.append("Tabela project_prototipo_prompt_versions já existe.")

    if not _table_exists(conn, "project_stitch_generations"):
        conn.execute(
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_project_stitch_generations_project_id "
            "ON project_stitch_generations (project_id)"
        )
        log.append("Criada tabela project_stitch_generations.")
    else:
        log.append("Tabela project_stitch_generations já existe.")
        cols = _columns(conn, "project_stitch_generations")
        if "approved_at" not in cols:
            conn.execute("ALTER TABLE project_stitch_generations ADD COLUMN approved_at DATETIME")
            log.append("Coluna project_stitch_generations.approved_at adicionada.")
        if "approved_by_email" not in cols:
            conn.execute("ALTER TABLE project_stitch_generations ADD COLUMN approved_by_email VARCHAR(255)")
            log.append("Coluna project_stitch_generations.approved_by_email adicionada.")
        if "export_storage_prefix" not in cols:
            conn.execute("ALTER TABLE project_stitch_generations ADD COLUMN export_storage_prefix VARCHAR(512)")
            log.append("Coluna project_stitch_generations.export_storage_prefix adicionada.")

    # project_task_columns (sub-Kanban por projeto)
    if not _table_exists(conn, "project_task_columns"):
        conn.execute(
            """
            CREATE TABLE project_task_columns (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                key VARCHAR(64) NOT NULL,
                title VARCHAR(128) NOT NULL,
                position INTEGER NOT NULL,
                color_hex VARCHAR(7) NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT fk_ptc_project FOREIGN KEY(project_id)
                    REFERENCES projects (id) ON DELETE CASCADE,
                CONSTRAINT uq_project_task_columns_project_key UNIQUE (project_id, key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_project_task_columns_project_id ON project_task_columns (project_id)"
        )
        log.append("Criada tabela project_task_columns.")
    else:
        log.append("Tabela project_task_columns já existe.")

    # app_settings (chave/valor encriptado para configuração futura)
    if not _table_exists(conn, "app_settings"):
        conn.execute(
            """
            CREATE TABLE app_settings (
                key VARCHAR(64) NOT NULL PRIMARY KEY,
                value_encrypted TEXT NOT NULL,
                hint_suffix VARCHAR(8)
            )
            """
        )
        log.append("Criada tabela app_settings.")
    else:
        log.append("Tabela app_settings já existe.")

    # system_general_settings (parâmetros gerais da UI de Configurações)
    if not _table_exists(conn, "system_general_settings"):
        conn.execute(
            """
            CREATE TABLE system_general_settings (
                id INTEGER NOT NULL PRIMARY KEY,
                org_name VARCHAR(255) NOT NULL,
                locale VARCHAR(32) NOT NULL,
                audit_strict INTEGER NOT NULL DEFAULT 1,
                ai_indexing INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        log.append("Criada tabela system_general_settings.")
    else:
        log.append("Tabela system_general_settings já existe.")

    conn.commit()
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra schema SQLite do projeto governança IA")
    default_db = Path(__file__).resolve().parent.parent / "dev.db"
    parser.add_argument("--db", type=Path, default=default_db, help="Caminho do ficheiro SQLite")
    args = parser.parse_args()
    db_path: Path = args.db

    if not db_path.is_file():
        print(f"Ficheiro não encontrado: {db_path}")
        print("Se ainda não correu a API, dev.db será criado no primeiro startup.")
        print("Se o ficheiro está doutro lado, use: python scripts/migrate_sqlite.py --db CAMINHO")
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        lines = migrate(conn)
        for line in lines:
            print(line)
        print("Migração concluída.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
