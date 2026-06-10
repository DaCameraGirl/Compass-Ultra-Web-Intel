select
    domain,
    count(*) as pages_crawled,
    max(fetched_at) as last_crawled_at,
    sum(feature_flag_mentions) as feature_flag_mentions,
    sum(release_process_mentions) as release_process_mentions,
    sum(compliance_mentions) as compliance_mentions,
    sum(workflow_mentions) as workflow_mentions,
    sum(pain_mentions) as pain_mentions,
    sum(compass_fit_score) as compass_fit_score,
    case
        when sum(compass_fit_score) >= 40 then 'high'
        when sum(compass_fit_score) >= 15 then 'medium'
        when sum(compass_fit_score) > 0 then 'low'
        else 'none'
    end as fit_tier
from {{ ref('fct_website_signals') }}
group by 1

