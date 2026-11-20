"""CLI for actor enrichment.

    python -m src.enrichment.cli enrich-starrers --max 100 --dry-run
    python -m src.enrichment.cli enrich-starrers --max 100
"""

import argparse
import logging
import sys

from src.config import Config
from src.enrichment import actor_fetcher
from src.enrichment.github_client import GitHubClient
from src.enrichment.store import DimActorsStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

REST_REQUESTS_PER_HOUR = 5_000


def cmd_enrich_starrers(args) -> int:
    config = Config.from_env()
    if not args.dry_run and not config.github_token:
        logger.error("GITHUB_TOKEN is not set (hint: export GITHUB_TOKEN=$(gh auth token))")
        return 2

    with DimActorsStore(config.metadata_db_url) as store:
        store.init_schema()
        fresh = store.fresh_actor_ids(args.ttl_days)
        in_scope, candidates = actor_fetcher.select_candidates(
            config, exclude=fresh, max_actors=args.max
        )

        print(
            f"Scope: {in_scope:,} human actors with "
            f"{'/'.join(actor_fetcher.ENRICH_EVENT_TYPES)} events\n"
            f"Fresh (enriched < {args.ttl_days}d ago, skipped): {len(fresh):,}\n"
            f"To fetch this run: {len(candidates):,}"
            + (f" (capped by --max {args.max})" if args.max is not None else "")
            + f"\nEstimated time at {REST_REQUESTS_PER_HOUR:,} req/h: "
            f"~{len(candidates) / REST_REQUESTS_PER_HOUR * 60:.0f} min"
        )
        if args.dry_run:
            print("\nFirst actors to fetch (busiest first):")
            for c in candidates[:10]:
                print(f"  {c.actor_id:>12}  {c.actor_login:<40} {c.event_count:>5} events")
            print("\nDry run: no API calls made.")
            return 0
        if not candidates:
            return 0

        with GitHubClient(config.github_token) as client:
            stats = actor_fetcher.enrich(client, store, candidates)
        logger.info("Done. %s; dim_actors now has %d rows", stats, store.count())
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.enrichment.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "enrich-starrers",
        help="Fetch GitHub profiles for actors with Watch/Fork/PR events",
    )
    p.add_argument("--max", type=int, help="Cap to the N busiest actors")
    p.add_argument("--ttl-days", type=int, default=30, help="Skip actors enriched more recently")
    p.add_argument("--dry-run", action="store_true", help="Show the plan; no API calls")
    p.set_defaults(func=cmd_enrich_starrers)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
