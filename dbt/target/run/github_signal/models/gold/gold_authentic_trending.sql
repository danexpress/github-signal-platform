
      create or replace view "warehouse"."main"."gold_authentic_trending__dbt_int" as (
        select * from read_parquet('s3://github-signal-raw/gold/authentic_trending/data.parquet', union_by_name=False)
        -- if relation is empty, filter by all columns having null values
        
      );
    