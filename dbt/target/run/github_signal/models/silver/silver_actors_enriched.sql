
      create or replace view "warehouse"."main"."silver_actors_enriched__dbt_int" as (
        select * from read_parquet('s3://github-signal-raw/silver/actors_enriched/data.parquet', union_by_name=False)
        -- if relation is empty, filter by all columns having null values
        
      );
    