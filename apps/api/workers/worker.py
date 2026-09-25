"""RQ worker entrypoint for background generation execution."""
from __future__ import annotations

import logging
import sys
from rq import Worker
from apps.api.queue import get_redis_connection, get_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("blog_agent.worker_main")


def run_worker() -> None:
    """Starts listening on the default RQ queue."""
    conn = get_redis_connection()
    queue = get_queue("default")
    logger.info("Starting Blog Agent RQ worker on queue: default...")
    worker = Worker([queue], connection=conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
        sys.exit(0)
