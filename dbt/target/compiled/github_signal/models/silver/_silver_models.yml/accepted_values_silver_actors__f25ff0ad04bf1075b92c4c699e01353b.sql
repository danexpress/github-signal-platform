
    
    

with all_values as (

    select
        lookup_status as value_field,
        count(*) as n_records

    from "warehouse"."main"."silver_actors_enriched"
    group by lookup_status

)

select *
from all_values
where value_field not in (
    'found','not_found'
)


