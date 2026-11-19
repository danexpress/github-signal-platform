{{
    config(
        materialized='external',
        location='s3://github-signal-raw/silver/events',
        format='parquet',
        options={'overwrite_or_ignore': true}
    )
}}

with raw as (
    -- DuckDB reads the full Parquet dataset in one go
    select *
    from read_parquet(
        's3://github-signal-raw/raw/gharchive/**/*.parquet',
        hive_partitioning = true,
        union_by_name = true
    )
),

parsed as (
    select
        -- Identity
        id as event_id,
        type as event_type,

        -- Actor
        actor_id,
        actor_login,
        -- Bot detection: GitHub app accounts end with [bot], many service accounts use -bot suffix
        case
            when actor_login ilike '%[bot]' then true
            when actor_login ilike '%-bot' then true
            when actor_login in ('dependabot', 'renovate', 'github-actions', 'codecov-io') then true
            else false
        end as actor_is_bot,

        -- Repo + Org
        repo_id,
        repo_name,
        org_id,
        org_login,

        -- Time
        created_at,
        cast(created_at as date) as event_date,
        extract(hour from created_at) as event_hour,

        -- Common payload fields (flattened out of JSON for typed access)
        -- Using try_* to tolerate schema drift across years
        try_cast(json_extract_string(payload_json, '$.action') as varchar) as payload_action,
        try_cast(json_extract_string(payload_json, '$.ref') as varchar) as payload_ref,
        try_cast(json_extract_string(payload_json, '$.ref_type') as varchar) as payload_ref_type,
        try_cast(json_extract(payload_json, '$.pull_request.number') as bigint) as pr_number,
        try_cast(json_extract(payload_json, '$.issue.number') as bigint) as issue_number,
        try_cast(json_extract(payload_json, '$.size') as integer) as push_commits_count,
        try_cast(json_extract(payload_json, '$.distinct_size') as integer) as push_distinct_commits,

        -- Keep raw payload for downstream enrichment
        payload_json,

        -- Audit from bronze
        

        -- Row-number for dedup (keep the most recently ingested version per event_id)
        row_number() over (
            partition by id
            order by created_at desc
        ) as _rn

    from raw
    where id is not null
      and type is not null
      and created_at is not null
)

select
    event_id,
    event_type,
    actor_id,
    actor_login,
    actor_is_bot,
    repo_id,
    repo_name,
    org_id,
    org_login,
    created_at,
    event_date,
    event_hour,
    payload_action,
    payload_ref,
    payload_ref_type,
    pr_number,
    issue_number,
    push_commits_count,
    push_distinct_commits,
    payload_json,
    current_timestamp as _processed_at
from parsed
where _rn = 1