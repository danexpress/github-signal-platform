
-- Every human starrer should have a profile row; >100 missing means enrichment is behind.
select actor_id
from "warehouse"."main"."silver_actors_enriched"
where stars_in_window > 0
  and not actor_is_bot
  and not is_enriched