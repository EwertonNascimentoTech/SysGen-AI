import importlib
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    audit,
    auth,
    cursor_hub,
    dashboard,
    directories,
    governance_rules,
    projects,
    system_settings,
    templates,
    users,
)
from app.core.config import settings
from app.db.base import Base
from app.db.schema_patch import (
    apply_governance_advance_rule_on_violation,
    apply_kanban_template_metadata_columns,
)
from app.db.session import async_session_maker, engine
from app.services.governance_seed import ensure_governance_advance_rules
from app.services.seed import seed_if_empty
from app.services.system_general_settings import ensure_system_general_settings_row

importlib.import_module("app.models")
from app.services.storage import ensure_bucket_exists


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(apply_kanban_template_metadata_columns)
        await conn.run_sync(apply_governance_advance_rule_on_violation)
    await anyio.to_thread.run_sync(ensure_bucket_exists)
    async with async_session_maker() as session:
        await seed_if_empty(session)
    async with async_session_maker() as session:
        await ensure_governance_advance_rules(session)
    async with async_session_maker() as session:
        await ensure_system_general_settings_row(session)
        await session.commit()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(governance_rules.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(cursor_hub.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(system_settings.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/ready")
async def health_ready():
    out: dict = {"database": True, "redis": False, "s3": bool(settings.s3_endpoint_url)}
    try:
        from app.services.queue_conn import get_redis

        get_redis().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out
