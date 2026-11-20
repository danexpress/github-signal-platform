# GitHub Signal Platform

An end-to-end data engineering project that ingests the public GitHub events 
firehose, lands it in a lakehouse, and surfaces actionable OSS intelligence 
signals.

Built as a portfolio project to demonstrate a modern, production-grade data 
stack: lakehouse ingestion, medallion architecture, dbt modeling, and 
analyst-ready signal detection.

## Key finding — why this isn't just a pipeline

Querying the top 10 trending repos by raw 24-hour star velocity surfaced 
mostly obscure drive-by projects, while high-signal repositories 
(anthropics/skills, microsoft/vscode, huggingface/transformers) registered 
only 1-12 stars in the same window.

**Raw star velocity is noise, not signal.** Any OSS trending product using 
it will mislead users. See [findings.md](./findings.md) for the full 
investigation.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   GH Archive    │     │     Bronze      │     │     Silver      │
│  (public data)  │────▶│  (raw Parquet)  │────▶│ (typed, deduped)│
│                 │     │                 │     │ event-type flat │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              MinIO                   MinIO
                           (S3 compat)             (S3 compat)
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │      Gold       │
                                              │  (analyst views)│
                                              │  [in progress]  │
                                              └─────────────────┘

Ingestion:  Python + boto3 + tenacity + Postgres (metadata/idempotency)
Transform:  dbt-duckdb reading directly from MinIO via httpfs
Serving:    DuckDB (zero-infra queries over Parquet)
Infra:      Docker Compose for MinIO + Postgres
```

## Stack

- **Ingestion:** Python 3.13, boto3, pyarrow, httpx, tenacity
- **Metadata:** Postgres (idempotency tracking per partition)
- **Lakehouse:** MinIO (S3-compatible), Parquet, Hive partitioning
- **Transformation:** dbt-duckdb, DuckDB httpfs extension
- **Local dev:** Docker Compose

## What's here

| Layer | Grain | Rows | Status |
|-------|-------|------|--------|
| Bronze | One row per GitHub event, partitioned `year=YYYY/month=MM/day=DD/hour=HH` | ~2M per day | ✅ Idempotent, retry-on-failure, metadata-tracked |
| Silver | One row per unique event, typed + flattened + bot-flagged | ~2M per day | ✅ Deduped on event_id, DQ tested |
| Gold | Analyst-ready aggregates | — | 🎯 In progress — reputation-weighted trending |

## Production-grade patterns implemented

- **Idempotency**: ingestion tracked in Postgres with `(source, partition_key)` 
  unique constraint. Re-running is safe.
- **Retry with exponential backoff**: via `tenacity` for all network calls.
- **Explicit Arrow schema**: pins column types across months of data drift, 
  ignores new fields gracefully.
- **Hive partitioning**: output matches Athena/Snowflake/DuckDB conventions 
  without configuration.
- **dbt tests**: unique, not_null, accepted_values on silver event types.
- **Data quality flags**: `actor_is_bot` derived in silver, not filtered — 
  downstream decides.

## Running locally

```bash
# Prerequisites: Docker, Python 3.11+
git clone <repo>
cd github-signal-platform

# Start MinIO + Postgres
docker compose up -d

# Install Python deps
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env

# Ingest a day of GH Archive data
python -m src.ingestion.cli backfill \
    --start 2026-10-01T00:00:00 \
    --end 2026-10-02T00:00:00 \
    --parallelism 4

# Build silver layer
cd dbt
dbt run --select silver_events
dbt test --select silver_events
```

## What's next

- `silver_actors_enriched`: GitHub REST API enrichment (account age, follower 
  count, prior activity)
- `gold_authentic_trending`: reputation-weighted trending signal
- Great Expectations contracts on top of dbt tests
- Streaming layer (Kafka + Flink) for real-time windowed counts
- FastAPI serving layer + minimal dashboard

## Why I built this

I'm a data engineer with 3+ years of ETL/ELT pipeline experience at Hootsuite. 
This project exists to demonstrate end-to-end lakehouse work in a modern stack: 
Python ingestion → Parquet in object storage → dbt-duckdb transforms → 
real analytical findings, not synthetic ones.

The real work is in the findings, not the plumbing. The pipeline exists to 
make findings possible. See [findings.md](./findings.md).