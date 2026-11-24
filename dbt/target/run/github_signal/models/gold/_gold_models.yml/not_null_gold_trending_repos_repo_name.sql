
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select repo_name
from "warehouse"."main"."gold_trending_repos"
where repo_name is null



  
  
      
    ) dbt_internal_test