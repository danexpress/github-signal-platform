-- depends_on: "warehouse"."main"."silver_events"



with events as (
    select *
    from read_parquet('s3://github-signal-raw/silver/events/*.parquet')
    where actor_is_bot = false
      and repo_id is not null
),

actors as (
    select
        actor_id,
        coalesce(reputation_score, 0.1) as reputation_score
    from read_parquet('s3://github-signal-raw/silver/actors_enriched/data.parquet')
),

actors_scored as (
    select
        actor_id,
        -- Reputation score (computed here so we don't depend on what's in actors_enriched)
        -- Range roughly 0 to 5+
        case
            when coalesce(status, 'missing') != 'enriched' then 0.1       -- unenriched baseline
            when coalesce(account_type, 'User') = 'Organization' then 2.5  -- orgs are real entities
            else
                0.3 * ln(coalesce(followers, 0) + 1)
                + 0.2 * ln(coalesce(public_repos, 0) + 1)
                + 0.1 * (
                    cast(coalesce(has_bio, false) as int)
                    + cast(coalesce(has_company, false) as int)
                    + cast(coalesce(has_location, false) as int)
                    + cast(coalesce(has_custom_avatar, false) as int)
                )
                + 0.4 * least(
                    date_diff('year', coalesce(github_created_at, current_timestamp)::timestamp, current_timestamp),
                    3.0
                )
        end as reputation_score
    from actors
),

event_weights(event_type, weight) as (
    values
        ('WatchEvent', 3.0),
        ('ForkEvent', 5.0),
        ('PullRequestEvent', 10.0),
        ('IssuesEvent', 2.0),
        ('ReleaseEvent', 15.0),
        ('PullRequestReviewEvent', 4.0)
),

weighted_events as (
    select
        e.repo_id,
        e.repo_name,
        e.event_type,
        e.actor_id,
        e.created_at,
        w.weight as event_weight,
        coalesce(a.reputation_score, 0.1) as actor_reputation,
        w.weight * coalesce(a.reputation_score, 0.1) as authentic_event_score
    from events e
    inner join event_weights w on e.event_type = w.event_type
    left join actors a on e.actor_id = a.actor_id  
    where (e.event_type != 'PullRequestEvent' or e.payload_action = 'opened')
      and (e.event_type != 'IssuesEvent' or e.payload_action = 'opened')
),

actor_repo_scores as (
    select
        repo_id,
        repo_name,
        actor_id,
        -- Cap each actor's contribution to one repo at 20 points
        -- Prevents single-actor bulk operations from dominating
        least(sum(authentic_event_score), 20.0) as capped_contribution,
        
        -- Also track per-actor stats for diagnostics
        sum(authentic_event_score)  as raw_contribution,
        count(*)                    as events_from_actor,
        max(actor_reputation)       as actor_reputation
    from weighted_events
    group by repo_id, repo_name, actor_id
),

repo_scored as (
    select
        repo_id,
        arg_max(repo_name, '2026-10-01'::date) as repo_name,  -- any value since no created_at here
        
        -- The capped score — diverse contributors beat single bulk actors
        sum(capped_contribution) as authentic_score,
        
        -- Raw uncapped score for comparison
        sum(raw_contribution) as raw_authentic_score,
        
        count(distinct actor_id)  as unique_actors,
        avg(actor_reputation)     as avg_actor_reputation,
        max(actor_reputation)     as max_actor_reputation,
        
        -- Concentration metric: what fraction of score comes from top 1 actor?
        max(raw_contribution) / nullif(sum(raw_contribution), 0) as top_actor_share,
        
        sum(events_from_actor) as total_events
    from actor_repo_scores
    group by repo_id
)

select
    repo_id,
    repo_name,
    round(authentic_score::numeric, 2) as authentic_score,
    round(raw_authentic_score::numeric, 2) as raw_authentic_score,
    unique_actors,
    round(avg_actor_reputation::numeric, 3) as avg_actor_reputation,
    round(top_actor_share::numeric, 3) as top_actor_share,
    total_events,
    current_timestamp as _processed_at
from repo_scored
where authentic_score > 0
order by authentic_score desc