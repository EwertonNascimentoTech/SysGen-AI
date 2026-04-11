from __future__ import annotations

import json
import uuid

from redis import Redis

from app.core.config import settings

_redis: Redis | None = None

WIKI_JOBS_KEY = "governanca:wiki_jobs"


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def enqueue_wiki_job(wiki_id: int, project_id: int, actor_user_id: int) -> str:
    job_id = str(uuid.uuid4())
    payload = json.dumps(
        {
            "job_id": job_id,
            "wiki_id": wiki_id,
            "project_id": project_id,
            "actor_user_id": actor_user_id,
        },
        separators=(",", ":"),
    )
    get_redis().lpush(WIKI_JOBS_KEY, payload)
    return job_id
