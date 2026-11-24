
    
    

select
    event_id as unique_field,
    count(*) as n_records

from "warehouse"."main"."silver_actors_enriched"
where event_id is not null
group by event_id
having count(*) > 1


