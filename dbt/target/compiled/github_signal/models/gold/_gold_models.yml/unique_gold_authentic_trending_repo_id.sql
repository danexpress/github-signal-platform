
    
    

select
    repo_id as unique_field,
    count(*) as n_records

from "warehouse"."main"."gold_authentic_trending"
where repo_id is not null
group by repo_id
having count(*) > 1


