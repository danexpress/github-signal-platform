
    
    

select
    repo_id as unique_field,
    count(*) as n_records

from "warehouse"."main"."gold_trending_repos"
where repo_id is not null
group by repo_id
having count(*) > 1


