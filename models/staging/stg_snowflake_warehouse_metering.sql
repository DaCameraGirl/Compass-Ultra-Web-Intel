select
    start_time,
    end_time,
    warehouse_id,
    warehouse_name,
    credits_used,
    credits_used_compute,
    credits_used_cloud_services
from {{ source('snowflake_account_usage', 'WAREHOUSE_METERING_HISTORY') }}
where start_time >= dateadd(day, -{{ var('lookback_days', 30) }}, current_timestamp())

