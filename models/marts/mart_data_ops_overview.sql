with connection_counts as (
    select
        count(*) as total_connections,
        count_if(health_state = 'healthy') as healthy_connections,
        count_if(health_state in ('failing', 'setup_issue', 'delayed', 'stale', 'never_synced')) as attention_connections,
        count_if(health_state = 'paused') as paused_connections,
        min(succeeded_at) as oldest_success_at,
        max(succeeded_at) as newest_success_at,
        max(observed_at) as fivetran_observed_at
    from {{ ref('fct_connection_health') }}
),

query_failures as (
    select
        count(*) as failed_queries_lookback,
        max(start_time) as most_recent_query_failure_at
    from {{ ref('fct_query_failures') }}
),

warehouse_usage as (
    select
        sum(credits_used) as credits_used_lookback,
        sum(estimated_compute_cost_usd) as estimated_compute_cost_usd_lookback
    from {{ ref('fct_warehouse_daily_cost') }}
)

select
    c.total_connections,
    c.healthy_connections,
    c.attention_connections,
    c.paused_connections,
    c.oldest_success_at,
    c.newest_success_at,
    c.fivetran_observed_at,
    q.failed_queries_lookback,
    q.most_recent_query_failure_at,
    w.credits_used_lookback,
    w.estimated_compute_cost_usd_lookback,
    current_timestamp() as modeled_at
from connection_counts as c
cross join query_failures as q
cross join warehouse_usage as w

