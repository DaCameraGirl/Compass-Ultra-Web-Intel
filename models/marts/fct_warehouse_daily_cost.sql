{% set credit_price = var('snowflake_credit_price_usd', '') %}

select
    to_date(start_time) as usage_date,
    warehouse_name,
    sum(credits_used) as credits_used,
    sum(credits_used_compute) as credits_used_compute,
    sum(credits_used_cloud_services) as credits_used_cloud_services,
    {% if credit_price | string | length > 0 %}
        sum(credits_used) * {{ credit_price }} as estimated_compute_cost_usd
    {% else %}
        cast(null as number(18, 2)) as estimated_compute_cost_usd
    {% endif %}
from {{ ref('stg_snowflake_warehouse_metering') }}
group by 1, 2

