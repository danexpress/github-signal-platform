"""CLI for running ingestion."""

import argparse
import logging
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import Config
from src.ingestion import gharchive, metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_backfill(args):
    config = Config.from_env()
    metadata.init_schema(config)

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    partitions = list(gharchive.hour_range(start, end))
    logger.info("Backfilling %d hours (%s → %s)", len(partitions), start, end)

    results = {"success": 0, "skipped": 0, "failed": 0}

    with ThreadPoolExecutor(max_workers=args.parallelism) as pool:
        futures = {
            pool.submit(gharchive.ingest_hour, config, p, force=args.force): p
            for p in partitions
        }
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                result = fut.result()
                results[result["status"]] += 1
            except Exception as e:
                logger.error("Partition %s failed: %s", p.key, e)
                results["failed"] += 1

    logger.info("Done. %s", results)
    return 0 if results["failed"] == 0 else 1


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    backfill = sub.add_parser("backfill", help="Ingest a range of hours")
    backfill.add_argument("--start", required=True, help="ISO datetime, inclusive")
    backfill.add_argument("--end", required=True, help="ISO datetime, exclusive")
    backfill.add_argument("--parallelism", type=int, default=4)
    backfill.add_argument(
        "--force", action="store_true", help="Re-ingest even if already succeeded"
    )
    backfill.set_defaults(func=cmd_backfill)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
