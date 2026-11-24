
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        enrichment_status as value_field,
        count(*) as n_records

    from "warehouse"."main"."silver_actors_enriched"
    group by enrichment_status

)

select *
from all_values
where value_field not in (
    'found','missing'
)



  
  
      
    ) dbt_internal_test