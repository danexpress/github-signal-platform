-- reputation_score is present exactly when the actor was found, and within the
-- formula's bounds: >= 0, and finite (ln terms are unbounded but sane < 10).
select event_id, actor_id, reputation_score, enrichment_status
from "warehouse"."main"."silver_actors_enriched"
where (enrichment_status = 'found') <> (reputation_score is not null)
   or reputation_score < 0
   or reputation_score > 10