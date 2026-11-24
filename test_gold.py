import duckdb

con = duckdb.connect()
con.execute("""
    INSTALL httpfs; LOAD httpfs;
    CREATE OR REPLACE SECRET minio_s3 (
        TYPE S3, KEY_ID 'ghsignal', SECRET 'ghsignal_dev_password',
        REGION 'us-east-1', ENDPOINT 'localhost:9000',
        URL_STYLE 'path', USE_SSL false
    );
""")

import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)

GOLD = "read_parquet('s3://github-signal-raw/gold/trending_repos/*.parquet')"

print("=" * 60)
print("TOP 10 BY WEIGHTED TRENDING SCORE")
print("=" * 60)
print(con.execute(f"""
    SELECT repo_name, trending_score, stars, forks, pr_opens, 
           issue_opens, releases, pr_reviews, is_stars_only
    FROM {GOLD}
    ORDER BY trending_score DESC
    LIMIT 10
""").fetchdf())

print("\n" + "=" * 60)
print("SUSPECTED STAR-BOMB CANDIDATES (stars only, no other activity)")
print("=" * 60)
print(con.execute(f"""
    SELECT repo_name, stars, unique_starrers
    FROM {GOLD}
    WHERE is_stars_only = true
    ORDER BY stars DESC
    LIMIT 10
""").fetchdf())

print("\n" + "=" * 60)
print("F1's TOP 10 RAW-COUNT REPOS — WHERE DO THEY RANK NOW?")
print("=" * 60)
f1_repos = [
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
repos_str = "', '".join(f1_repos)
print(con.execute(f"""
    WITH ranked AS (
        SELECT repo_name, trending_score, stars, forks, pr_opens, is_stars_only,
               ROW_NUMBER() OVER (ORDER BY trending_score DESC) AS weighted_rank
        FROM {GOLD}
    )
    SELECT repo_name, weighted_rank, trending_score, stars, forks, pr_opens, is_stars_only
    FROM ranked
    WHERE repo_name IN ('{repos_str}')
    ORDER BY weighted_rank
""").fetchdf())

print("\n" + "=" * 60)
print("KNOWN HIGH-SIGNAL REPOS — DO THEY SURFACE NOW?")
print("=" * 60)
print(con.execute(f"""
    WITH ranked AS (
        SELECT repo_name, trending_score, stars, forks, pr_opens,
               ROW_NUMBER() OVER (ORDER BY trending_score DESC) AS weighted_rank
        FROM {GOLD}
    )
    SELECT repo_name, weighted_rank, trending_score, stars, forks, pr_opens
    FROM ranked
    WHERE repo_name LIKE 'anthropics/%'
       OR repo_name LIKE 'microsoft/%'
       OR repo_name LIKE 'openai/%'
       OR repo_name LIKE 'huggingface/%'
       OR repo_name LIKE 'vercel/%'
    ORDER BY weighted_rank
    LIMIT 20
""").fetchdf())
