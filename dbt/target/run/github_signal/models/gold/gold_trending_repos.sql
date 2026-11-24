
      create or replace view "warehouse"."main"."gold_trending_repos__dbt_int" as (
        select * from read_parquet('s3://github-signal-raw/gold/trending_repos/data.parquet', union_by_name=False)
        -- if relation is empty, filter by all columns having null values
        
      );
    