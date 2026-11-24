
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_enriched
from "warehouse"."main"."silver_actors_enriched"
where is_enriched is null



  
  
      
    ) dbt_internal_test