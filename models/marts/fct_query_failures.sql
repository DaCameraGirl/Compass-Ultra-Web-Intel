select
    query_id,
    start_time,
    end_time,
    warehouse_name,
    user_name,
    role_name,
    database_name,
    schema_name,
    query_type,
    error_code,
    error_message,
    query_text,
    total_elapsed_time,
    bytes_scanned
from {{ ref('stg_snowflake_query_history') }}
where execution_status in ('fail', 'incident')

