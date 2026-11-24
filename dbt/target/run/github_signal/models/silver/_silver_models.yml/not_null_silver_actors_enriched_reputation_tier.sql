
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select reputation_tier
from "warehouse"."main"."silver_actors_enriched"
where reputation_tier is null



  
  
      
    ) dbt_internal_test