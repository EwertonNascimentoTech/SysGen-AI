from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.project_cursor_agent_run import CursorWebhookDelivery, ProjectCursorAgentRun
from app.services.cursor_agent_board import AGENT_FINISHED_STATUSES, move_task_to_review_after_agent_finish
from app.services.cursor_cloud_agents import verify_cursor_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/cursor-agent")
async def cursor_agent_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    secret = (settings.cursor_webhook_secret or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook não configurado no servidor")

    raw = await request.body()
    sig = request.headers.get("X-Webhook-Signature")
    if not verify_cursor_webhook_signature(secret, raw, sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura inválida")

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("cursor webhook: corpo JSON inválido: %s", e)
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    agent_id = str(payload.get("id") or "").strip()
    new_status = str(payload.get("status") or "").strip().upper()

    if not agent_id:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    run = (
        await session.execute(select(ProjectCursorAgentRun).where(ProjectCursorAgentRun.cursor_agent_id == agent_id))
    ).scalar_one_or_none()
    if not run:
        logger.info("cursor webhook: agente desconhecido %s (ignorado)", agent_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    webhook_id = (request.headers.get("X-Webhook-ID") or "").strip()
    if webhook_id:
        dup = (
            await session.execute(select(CursorWebhookDelivery).where(CursorWebhookDelivery.webhook_id == webhook_id))
        ).scalar_one_or_none()
        if dup is not None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        session.add(CursorWebhookDelivery(webhook_id=webhook_id))

    run.status = new_status or run.status
    if isinstance(payload.get("summary"), str):
        run.summary = (payload.get("summary") or "")[:8000] or None

    if new_status in AGENT_FINISHED_STATUSES:
        await move_task_to_review_after_agent_finish(session, run, agent_id)

    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
