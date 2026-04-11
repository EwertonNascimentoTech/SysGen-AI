def normalize_async_database_url(url: str) -> str:
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql+asyncpg://" + u[len("postgres://") :]
    elif u.startswith("postgresql://") and "+asyncpg" not in u and "+psycopg" not in u:
        u = "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u


def to_sync_database_url(url: str) -> str:
    """URL síncrona para RQ: SQLite nativo; PostgreSQL via driver pg8000 (sem binários)."""
    u = url.strip()
    u = u.replace("sqlite+aiosqlite:", "sqlite:")
    u = u.replace("postgresql+asyncpg:", "postgresql+pg8000:")
    u = u.replace("postgresql+psycopg:", "postgresql+pg8000:")
    u = u.replace("postgresql+psycopg2:", "postgresql+pg8000:")
    u = u.replace("postgresql+psycopg_async:", "postgresql+pg8000:")
    if u.startswith("postgres://"):
        u = "postgresql+pg8000://" + u[len("postgres://") :]
    elif u.startswith("postgresql://") and "+pg8000" not in u and "+asyncpg" not in u:
        u = "postgresql+pg8000://" + u[len("postgresql://") :]
    return u
