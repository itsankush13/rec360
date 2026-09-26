"""
Local queue drainer — the Windows-friendly stand-in for an RQ worker.

Processes jobs the deferred backend left in QUEUED. Needs no Redis, no Docker
and no fork, so it runs anywhere Python does.

    python scripts/run_worker.py                 # drain once, then exit
    python scripts/run_worker.py --watch         # keep polling
    python scripts/run_worker.py --batch <id>    # only one batch
    python scripts/run_worker.py --limit 50      # cap files this pass

Run it in a second terminal alongside uvicorn. It processes one file at a time
by design: concurrent writers against SQLite hit database-level write locking,
so real parallelism needs Postgres and the rq backend.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workers import tasks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", default=None, help="restrict to one batch id")
    parser.add_argument("--limit", type=int, default=None, help="max files this pass")
    parser.add_argument("--watch", action="store_true", help="keep polling for new work")
    parser.add_argument("--interval", type=float, default=2.0, help="poll seconds (--watch)")
    args = parser.parse_args()

    if not args.watch:
        result = tasks.drain_pending(batch_id=args.batch, limit=args.limit)
        print(f"Processed {result['processed']} file(s); {result['remaining']} still queued.")
        return 0

    print("Watching for queued CVs. Ctrl+C to stop.")
    try:
        while True:
            result = tasks.drain_pending(batch_id=args.batch, limit=args.limit)
            if result["processed"]:
                print(f"  processed {result['processed']}, {result['remaining']} remaining")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
