
    
    

with all_values as (

    select
        reputation_tier as value_field,
        count(*) as n_records

    from "warehouse"."main"."silver_actors_enriched"
    group by reputation_tier

)

select *
from all_values
where value_field not in (
    'high','medium','low','unknown','gone','bot'
)


