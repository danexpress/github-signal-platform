
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

select
    actor_id as unique_field,
    count(*) as n_records

from "warehouse"."main"."silver_actors_enriched"
where actor_id is not null
group by actor_id
having count(*) > 1



  
  
      
    ) dbt_internal_test