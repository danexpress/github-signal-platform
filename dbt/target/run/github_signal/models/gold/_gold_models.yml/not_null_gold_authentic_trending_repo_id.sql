
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select repo_id
from "warehouse"."main"."gold_authentic_trending"
where repo_id is null



  
  
      
    ) dbt_internal_test