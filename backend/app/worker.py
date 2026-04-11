"""Worker de fila Wiki (Redis). Execute: python -m app.worker"""

import json
import logging
import time

from app.jobs.wiki_job import run_generate_wiki
from app.services.queue_conn import WIKI_JOBS_KEY, get_redis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("wiki-worker")


def main() -> None:
    r = get_redis()
    log.info("Wiki worker aguardando jobs em %s …", WIKI_JOBS_KEY)
    while True:
        item = r.brpop(WIKI_JOBS_KEY, timeout=30)
        if not item:
            continue
        _, raw = item
        try:
            data = json.loads(raw)
            run_generate_wiki(
                int(data["wiki_id"]),
                int(data["project_id"]),
                int(data["actor_user_id"]),
            )
            log.info("Wiki job ok wiki_id=%s", data.get("wiki_id"))
        except Exception as e:
            log.exception("Falha no job: %s", e)
            time.sleep(1)


if __name__ == "__main__":
    main()
