import duckdb
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)

con = duckdb.connect()
con.execute("""
    INSTALL httpfs; LOAD httpfs;
    CREATE OR REPLACE SECRET minio_s3 (
        TYPE S3, KEY_ID 'ghsignal', SECRET 'ghsignal_dev_password',
        REGION 'us-east-1', ENDPOINT 'localhost:9000',
        URL_STYLE 'path', USE_SSL false
    );
""")

AUTHENTIC = "read_parquet('s3://github-signal-raw/gold/authentic_trending/*.parquet')"
WEIGHTED = "read_parquet('s3://github-signal-raw/gold/trending_repos/*.parquet')"

print("=" * 70)
print("TOP 15 BY AUTHENTIC (REPUTATION-WEIGHTED, DIVERSITY-CAPPED) SCORE")
print("=" * 70)
print(con.execute(f"""
    SELECT repo_name, authentic_score, raw_authentic_score, 
           unique_actors, avg_actor_reputation, top_actor_share, total_events
    FROM {AUTHENTIC}
    ORDER BY authentic_score DESC
    LIMIT 15
""").fetchdf())

print("\n" + "=" * 70)
print("THREE-WAY COMPARISON: RAW STARS vs WEIGHTED EVENTS vs AUTHENTIC")
print("=" * 70)
print("\nF2's weighted top 10 — where do they land under reputation weighting?")
print(con.execute(f"""
    WITH authentic_ranked AS (
        SELECT repo_name,
               ROW_NUMBER() OVER (ORDER BY authentic_score DESC) AS authentic_rank,
               authentic_score, avg_actor_reputation
        FROM {AUTHENTIC}
    ),
    weighted_top10 AS (
        SELECT repo_name
        FROM {WEIGHTED}
        ORDER BY trending_score DESC
        LIMIT 10
    )
    SELECT w.repo_name, a.authentic_rank, a.authentic_score, a.avg_actor_reputation
    FROM weighted_top10 w
    LEFT JOIN authentic_ranked a ON w.repo_name = a.repo_name
    ORDER BY a.authentic_rank NULLS LAST
""").fetchdf())

print("\nDo known heavyweights now surface?")
print(con.execute(f"""
    WITH authentic_ranked AS (
        SELECT repo_name,
               ROW_NUMBER() OVER (ORDER BY authentic_score DESC) AS authentic_rank,
               authentic_score, avg_actor_reputation
        FROM {AUTHENTIC}
    )
    SELECT repo_name, authentic_rank, authentic_score, avg_actor_reputation
    FROM authentic_ranked
    WHERE repo_name LIKE 'anthropics/%'
       OR repo_name LIKE 'microsoft/%'
       OR repo_name LIKE 'openai/%'
       OR repo_name LIKE 'huggingface/%'
       OR repo_name LIKE 'vercel/%'
       OR repo_name LIKE 'facebook/%'
       OR repo_name LIKE 'vuejs/%'
    ORDER BY authentic_rank
    LIMIT 20
""").fetchdf())

print("\n" + "=" * 70)
print("REPUTATION DISTRIBUTION — top-ranked repos by avg actor reputation")
print("=" * 70)
print(con.execute(f"""
    WITH ranks AS (
        SELECT repo_name,
               ROW_NUMBER() OVER (ORDER BY authentic_score DESC) AS rank
        FROM {AUTHENTIC}
    )
    SELECT
        CASE 
            WHEN rank <= 10 THEN '1. top 10'
            WHEN rank <= 100 THEN '2. top 100'
            WHEN rank <= 1000 THEN '3. top 1k'
            ELSE '4. the long tail'
        END AS tier,
        COUNT(*) AS repos,
        ROUND(AVG(a.avg_actor_reputation)::numeric, 3) AS avg_reputation,
        ROUND(AVG(a.authentic_score)::numeric, 2) AS avg_score
    FROM {AUTHENTIC} a
    JOIN ranks r USING (repo_name)
    GROUP BY 1
    ORDER BY 1
""").fetchdf())
