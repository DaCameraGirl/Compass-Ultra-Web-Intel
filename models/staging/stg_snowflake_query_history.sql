select
    query_id,
    query_text,
    database_name,
    schema_name,
    query_type,
    user_name,
    role_name,
    warehouse_name,
    warehouse_size,
    query_tag,
    execution_status,
    error_code,
    error_message,
    start_time,
    end_time,
    total_elapsed_time,
    bytes_scanned,
    rows_inserted,
    rows_updated,
    rows_deleted
from {{ source('snowflake_account_usage', 'QUERY_HISTORY') }}
where start_time >= dateadd(day, -{{ var('lookback_days', 30) }}, current_timestamp())

