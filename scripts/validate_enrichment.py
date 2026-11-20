"""Validate the F1 hypothesis against silver_actors_enriched.

Run after:  cd dbt && dbt run --select silver_actors_enriched

H1: the top-10 raw-star repos from F1 are starred predominantly by 'low'
    reputation accounts.
H2: known high-signal repos are starred predominantly by 'medium'/'high'
    reputation accounts.

Shares are computed over *enriched* starrers only (found or missing); coverage
is reported so a thin sample isn't mistaken for a result.
"""

import os
import sys
from urllib.parse import urlparse

import duckdb

F1_TOP10 = [
    "Niko1221/Strata",
    "debpalash/VoiceStudio",
    "eternity4719/HowToLiveBetter",
    "DietrichGebert/ponytail",
    "NVIDIA/OpenShell",
    "ifixai-ai/iFixAi",
    "Panniantong/Agent-Reach",
    "nanaism/yomiyasu",
    "OffGridPete/Fieldwatch",
    "walkinglabs/learn-harness-engineering",
]
HIGH_SIGNAL = [
    "anthropics/skills",
    "anthropics/claude-code",
    "microsoft/markitdown",
    "anthropics/financial-services",
    "openai/mcp-extensions",
    "microsoft/vscode",
    "huggingface/transformers",
]
MIN_COVERAGE = 0.8  # below this, verdicts are reported as inconclusive


def connect() -> duckdb.DuckDBPyConnection:
    endpoint = urlparse(os.environ.get("S3_ENDPOINT", "http://localhost:9000"))
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE SECRET lake (TYPE S3, KEY_ID ?, SECRET ?, REGION ?, ENDPOINT ?, "
        "URL_STYLE 'path', USE_SSL ?)",
        [
            os.environ.get("S3_ACCESS_KEY", "ghsignal"),
            os.environ.get("S3_SECRET_KEY", "ghsignal_dev_password"),
            os.environ.get("S3_REGION", "us-east-1"),
            endpoint.netloc,
            endpoint.scheme == "https",
        ],
    )
    bucket = os.environ.get("S3_RAW_BUCKET", "github-signal-raw")
    con.execute(
        f"""
        create temp table starred_by as
        select distinct
            case when repo_name in (select unnest(?)) then 'F1 top-10'
                 else 'High-signal' end as cohort,
            repo_name, actor_id, reputation_tier, reputation_score, is_newly_created
        from read_parquet('s3://{bucket}/silver/actors_enriched/data.parquet')
        where event_type = 'WatchEvent'
          and not actor_is_bot
          and repo_name in (select unnest(?))
        """,
        [F1_TOP10, F1_TOP10 + HIGH_SIGNAL],
    )
    return con


TIER_SHARES = """
    count(*)                                                        as starrers,
    count(*) filter (where reputation_tier <> 'unenriched')         as enriched,
    round(100.0 * enriched / starrers, 0)                           as coverage_pct,
    round(100.0 * count(*) filter (where reputation_tier = 'high')   / nullif(enriched, 0), 1) as high_pct,
    round(100.0 * count(*) filter (where reputation_tier = 'medium') / nullif(enriched, 0), 1) as medium_pct,
    round(100.0 * count(*) filter (where reputation_tier = 'low')    / nullif(enriched, 0), 1) as low_pct,
    round(100.0 * count(*) filter (where reputation_tier = 'missing')/ nullif(enriched, 0), 1) as missing_pct,
    round(100.0 * count(*) filter (where is_newly_created)           / nullif(enriched, 0), 1) as new_acct_pct,
    round(median(reputation_score), 2)                               as median_score
"""


def main() -> int:
    con = connect()

    print("\n=== Reputation distribution of starrers, by cohort (% of enriched) ===")
    by_cohort = con.sql(f"select cohort, {TIER_SHARES} from starred_by group by 1 order by 1")
    by_cohort.show(max_width=250)

    print("=== Per repo ===")
    con.sql(
        f"select cohort, repo_name, {TIER_SHARES} from starred_by group by 1, 2 "
        "order by 1, starrers desc"
    ).show(max_rows=50, max_width=250)

    results = {row[0]: row for row in by_cohort.fetchall()}
    cols = [d[0] for d in by_cohort.description]

    def get(cohort: str, col: str):
        row = results.get(cohort)
        return row[cols.index(col)] if row else None

    def verdict(cohort: str, holds: bool | None) -> str:
        coverage = (get(cohort, "coverage_pct") or 0) / 100
        if holds is None or coverage < MIN_COVERAGE:
            return f"INCONCLUSIVE (coverage {coverage:.0%} < {MIN_COVERAGE:.0%}; run enrichment further)"
        return "HOLDS" if holds else "DOES NOT HOLD"

    low = get("F1 top-10", "low_pct")
    good = None
    if get("High-signal", "enriched"):
        good = (get("High-signal", "high_pct") or 0) + (get("High-signal", "medium_pct") or 0)

    print(f"H1  F1 top-10 starrers predominantly 'low' ({low}% low):  "
          f"{verdict('F1 top-10', None if low is None else low > 50)}")
    print(f"H2  High-signal starrers predominantly medium/high ({good}%):  "
          f"{verdict('High-signal', None if good is None else good > 50)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
