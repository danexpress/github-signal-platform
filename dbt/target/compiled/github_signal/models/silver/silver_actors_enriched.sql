

-- Grain: one row per silver event, with the acting user's profile attached.
-- Actors are enriched only for Watch/Fork/PR events (see src/enrichment), so
-- push-only actors carry null profile fields and reputation_tier='unenriched'.
--
-- reputation_score is a V1 HEURISTIC, NOT A TRAINED MODEL. Weights were chosen
-- by hand to separate drive-by accounts from established developers, and have
-- not been fitted or validated against labelled data. Range is roughly 0-5:
--     0.3 * ln(followers + 1)
--   + 0.2 * ln(public_repos + 1)
--   + 0.1 * (has_bio + has_company + has_location + has_custom_avatar)
--   + 0.4 * least(account_age_years, 3)          -- capped at 3 years
-- Account age is measured at event time, so the score is reproducible.

with events as (
    select
        event_id,
        event_type,
        actor_id,
        actor_login,
        actor_is_bot,
        repo_id,
        repo_name,
        created_at,
        event_date
    from "warehouse"."main"."silver_events"
),

actors as (
    select * from "meta"."public"."dim_actors"
),

joined as (
    select
        e.*,
        a.actor_id is not null                                        as is_enriched,
        a.status                                                      as enrichment_status,
        a.login                                                       as profile_login,
        a.user_type,
        a.account_created_at,
        a.followers,
        a.following,
        a.public_repos,
        a.has_bio,
        a.has_company,
        a.has_location,
        a.has_custom_avatar,
        a._enriched_at,
        date_diff('day', a.account_created_at, e.created_at)          as account_age_days
    from events e
    left join actors a using (actor_id)
),

scored as (
    select
        *,
        account_age_days < 30                                         as is_newly_created,
        case when enrichment_status = 'found' then round(
              0.3 * ln(coalesce(followers, 0) + 1)
            + 0.2 * ln(coalesce(public_repos, 0) + 1)
            + 0.1 * ( coalesce(has_bio, false)::int
                    + coalesce(has_company, false)::int
                    + coalesce(has_location, false)::int
                    + coalesce(has_custom_avatar, false)::int )  -- null avatar check counts as 0
            + 0.4 * least(greatest(account_age_days, 0) / 365.0, 3.0)
        , 3) end                                                      as reputation_score
    from joined
)

select
    *,
    case
        -- Spec tiers are high/medium/low. Two extra states keep unknowns from
        -- being silently counted as 'low', which would bias validation toward
        -- confirming F1.
        when not is_enriched                then 'unenriched'
        when enrichment_status = 'missing'  then 'missing'
        when reputation_score > 3           then 'high'
        when reputation_score > 1           then 'medium'
        else 'low'
    end                                                               as reputation_tier,
    current_timestamp                                                 as _processed_at
from scored