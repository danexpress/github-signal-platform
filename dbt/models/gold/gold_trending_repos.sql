-- depends_on: {{ ref('silver_events') }}

{{
    config(
        materialized='external',
        location='s3://github-signal-raw/gold/trending_repos/data.parquet',
        format='parquet',
        options={'overwrite_or_ignore': 1}
    )
}}

with events as (
    select *
    from read_parquet('s3://github-signal-raw/silver/events/*.parquet')
    where actor_is_bot = false      -- gold is human-signal only
),

repo_counts as (
    select
        repo_id,
        arg_max(repo_name, created_at) as repo_name,   -- latest name per repo_id

        -- Event counts per repo (these stay the same)
        count(*) filter (where event_type = 'WatchEvent')                    as stars,
        count(*) filter (where event_type = 'ForkEvent')                     as forks,
        count(*) filter (
            where event_type = 'PullRequestEvent' and payload_action = 'opened'
        )                                                                    as pr_opens,
        count(*) filter (
            where event_type = 'IssuesEvent' and payload_action = 'opened'
        )                                                                    as issue_opens,
        count(*) filter (where event_type = 'ReleaseEvent')                  as releases,
        count(*) filter (where event_type = 'PushEvent')                     as pushes,
        count(*) filter (where event_type = 'PullRequestReviewEvent')        as pr_reviews,

        count(distinct case when event_type = 'WatchEvent' then actor_id end)       as unique_starrers,
        count(distinct case when event_type = 'ForkEvent' then actor_id end)        as unique_forkers,
        count(distinct case when event_type = 'PullRequestEvent' then actor_id end) as unique_pr_authors,
        count(distinct actor_id)                                             as unique_human_actors,

        min(created_at)                                                      as first_event_at,
        max(created_at)                                                      as last_event_at
    from events
    where repo_id is not null
    group by repo_id                                 -- only repo_id in GROUP BY
),

scored as (
    select
        *,

        -- Composite trending score — weighted by signal strength
        -- Forks and PRs beat stars because they require more intent
        (
            stars * 3
            + forks * 5
            + pr_opens * 10
            + issue_opens * 2
            + releases * 15
            + pr_reviews * 4
        ) as trending_score,

        -- A simpler "engagement depth" ratio
        case
            when stars = 0 then null
            else round(forks::numeric / stars, 3)
        end as fork_to_star_ratio,

        -- Flags for suspicious patterns (narrow, high-count = star bomb signal)
        case
            when stars > 20 and forks = 0 and pr_opens = 0 and issue_opens = 0
                then true else false
        end as is_stars_only

    from repo_counts
)

select
    repo_id,
    repo_name,
    trending_score,
    stars,
    forks,
    pr_opens,
    issue_opens,
    releases,
    pr_reviews,
    pushes,
    unique_starrers,
    unique_forkers,
    unique_pr_authors,
    unique_human_actors,
    fork_to_star_ratio,
    is_stars_only,
    first_event_at,
    last_event_at,
    current_timestamp as _processed_at
from scored
where trending_score > 0
order by trending_score desc