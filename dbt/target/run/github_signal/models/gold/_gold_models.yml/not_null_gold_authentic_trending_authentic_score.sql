
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select authentic_score
from "warehouse"."main"."gold_authentic_trending"
where authentic_score is null



  
  
      
    ) dbt_internal_test