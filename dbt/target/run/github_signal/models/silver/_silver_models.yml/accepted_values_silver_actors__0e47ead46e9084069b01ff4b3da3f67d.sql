
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        reputation_tier as value_field,
        count(*) as n_records

    from "warehouse"."main"."silver_actors_enriched"
    group by reputation_tier

)

select *
from all_values
where value_field not in (
    'high','medium','low','unknown','gone','bot'
)



  
  
      
    ) dbt_internal_test