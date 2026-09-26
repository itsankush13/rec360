"""
RQ worker entrypoint (Linux / production only).

    python -m app.workers.worker

RQ forks to isolate jobs, so this will not run on Windows. For local Windows
development use the deferred backend and drain the queue with
`python scripts/run_worker.py`, which needs neither Redis nor fork.
"""
from __future__ import annotations

import os
import sys

from app.workers.queue import DEFAULT_QUEUE_NAME, redis_url


def main() -> int:
    if sys.platform.startswith("win"):
        print(
            "RQ workers cannot run on Windows (RQ relies on os.fork).\n"
            "Use the deferred queue backend instead:\n"
            "    $env:QUEUE_BACKEND = 'deferred'\n"
            "    python scripts/run_worker.py --watch",
            file=sys.stderr,
        )
        return 1

    from redis import Redis
    from rq import Queue, Worker

    connection = Redis.from_url(redis_url())
    queue_name = os.getenv("QUEUE_NAME", DEFAULT_QUEUE_NAME)
    print(f"Starting RQ worker on '{queue_name}' via {redis_url()}")
    Worker([Queue(queue_name, connection=connection)], connection=connection).work()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
