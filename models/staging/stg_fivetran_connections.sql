with source as (
    select
        connection_id,
        group_id,
        service,
        schema_name,
        paused,
        setup_state,
        sync_state,
        update_state,
        succeeded_at,
        failed_at,
        created_at,
        sync_frequency_minutes,
        schedule_type,
        loaded_at
    from {{ source('fivetran_api', 'CONNECTIONS') }}
),

classified as (
    select
        *,
        case
            when paused then 'paused'
            when setup_state is null then 'unknown'
            when setup_state != 'connected' then 'setup_issue'
            when update_state = 'delayed' then 'delayed'
            when failed_at is not null and (succeeded_at is null or failed_at > succeeded_at) then 'failing'
            when succeeded_at is null then 'never_synced'
            when succeeded_at < dateadd(
                minute,
                -greatest(coalesce(sync_frequency_minutes, 360) * 2, 120),
                current_timestamp()
            ) then 'stale'
            else 'healthy'
        end as health_state,
        datediff(minute, succeeded_at, current_timestamp()) as minutes_since_success,
        datediff(minute, failed_at, current_timestamp()) as minutes_since_failure
    from source
)

select * from classified

