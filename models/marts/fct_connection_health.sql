select
    c.connection_id,
    c.group_id,
    g.group_name,
    c.service,
    c.schema_name,
    c.paused,
    c.setup_state,
    c.sync_state,
    c.update_state,
    c.health_state,
    c.succeeded_at,
    c.failed_at,
    c.minutes_since_success,
    c.minutes_since_failure,
    c.sync_frequency_minutes,
    c.schedule_type,
    c.loaded_at as observed_at
from {{ ref('stg_fivetran_connections') }} as c
left join {{ ref('stg_fivetran_groups') }} as g
    on c.group_id = g.group_id

