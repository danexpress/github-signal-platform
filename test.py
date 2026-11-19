import duckdb
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

con = duckdb.connect()
con.execute("""
    INSTALL httpfs; LOAD httpfs;
    CREATE OR REPLACE SECRET minio_s3 (
        TYPE S3, KEY_ID 'ghsignal', SECRET 'ghsignal_dev_password',
        REGION 'us-east-1', ENDPOINT 'localhost:9000',
        URL_STYLE 'path', USE_SSL false
    );
""")

SILVER = "read_parquet('s3://github-signal-raw/silver/*')"

print("=== Overview ===")
# 1. Are the same actors starring multiple of the top 10? (coordinated inauthentic behavior)
print(con.execute(f"""
    WITH top_repos AS (
        SELECT repo_name
        FROM {SILVER}
        WHERE event_type = 'WatchEvent' AND actor_is_bot = false
        GROUP BY repo_name
        ORDER BY COUNT(*) DESC
        LIMIT 10
    ),
    starrers AS (
        SELECT actor_id, actor_login, repo_name
        FROM {SILVER}
        WHERE event_type = 'WatchEvent' 
          AND repo_name IN (SELECT repo_name FROM top_repos)
    )
    SELECT actor_login, COUNT(DISTINCT repo_name) AS repos_starred
    FROM starrers
    GROUP BY actor_id, actor_login
    HAVING COUNT(DISTINCT repo_name) > 1
    ORDER BY repos_starred DESC
    LIMIT 20
""").fetchdf())

# 2. Are the stars bunched in time? (botnet pattern)
print(con.execute(f"""
    SELECT repo_name, 
           MIN(created_at) AS first_star,
           MAX(created_at) AS last_star,
           EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))/60 AS span_minutes,
           COUNT(*) AS stars
    FROM {SILVER}
    WHERE event_type = 'WatchEvent'
      AND repo_name IN (
          SELECT repo_name FROM {SILVER}
          WHERE event_type = 'WatchEvent' AND actor_is_bot = false
          GROUP BY repo_name ORDER BY COUNT(*) DESC LIMIT 10
      )
    GROUP BY repo_name
    ORDER BY stars DESC
""").fetchdf())

# 3. Do the starring actors have any OTHER activity? (real users do; bots mostly don't)
print(con.execute(f"""
    WITH top_repo_starrers AS (
        SELECT DISTINCT actor_id
        FROM {SILVER}
        WHERE event_type = 'WatchEvent'
          AND repo_name = 'Niko1221/Strata'
    )
    SELECT 
        COUNT(*) AS total_starrers,
        SUM(CASE WHEN other_events > 0 THEN 1 ELSE 0 END) AS starrers_with_other_activity,
        SUM(CASE WHEN other_events = 0 THEN 1 ELSE 0 END) AS starrers_with_NO_other_activity
    FROM (
        SELECT t.actor_id,
               COUNT(CASE WHEN e.event_type != 'WatchEvent' THEN 1 END) AS other_events
        FROM top_repo_starrers t
        LEFT JOIN {SILVER} e ON t.actor_id = e.actor_id
        GROUP BY t.actor_id
    )
""").fetchdf())
print(con.execute(f"""
    SELECT repo_name, COUNT(*) AS stars
    FROM {SILVER}
    WHERE event_type = 'WatchEvent'
      AND actor_is_bot = false
      AND (
        repo_name LIKE 'facebook/%' OR
        repo_name LIKE 'vuejs/%' OR
        repo_name LIKE 'microsoft/%' OR
        repo_name LIKE 'vercel/%' OR
        repo_name LIKE 'anthropics/%' OR
        repo_name LIKE 'openai/%' OR
        repo_name LIKE 'nvidia/%' OR
        repo_name LIKE 'huggingface/%'
      )
    GROUP BY repo_name
    ORDER BY stars DESC
    LIMIT 20
""").fetchdf())
