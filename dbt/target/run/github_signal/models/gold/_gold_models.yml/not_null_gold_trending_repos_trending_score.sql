
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select trending_score
from "warehouse"."main"."gold_trending_repos"
where trending_score is null



  
  
      
    ) dbt_internal_test