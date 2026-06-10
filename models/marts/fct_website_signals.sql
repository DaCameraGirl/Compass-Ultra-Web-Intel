select
    url,
    domain,
    title,
    meta_description,
    fetched_at,
    body_char_count,
    regexp_count(search_text, 'feature flag|feature flags|launchdarkly|unleash|flagsmith|openfeature|statsig|remote config') as feature_flag_mentions,
    regexp_count(search_text, 'release|deploy|deployment|rollback|canary|change advisory|cab|production incident') as release_process_mentions,
    regexp_count(search_text, 'audit|compliance|sox|hipaa|soc 2|security review|change management') as compliance_mentions,
    regexp_count(search_text, 'pricing|trial|free|enterprise|contact sales|per month') as pricing_mentions,
    regexp_count(search_text, 'slack|jira|github|ci/cd|workflow|runbook') as workflow_mentions,
    regexp_count(search_text, 'stale flag|flag debt|technical debt|owner|approver|approval') as pain_mentions,
    (
        regexp_count(search_text, 'feature flag|feature flags|launchdarkly|unleash|flagsmith|openfeature|statsig|remote config') * 3
        + regexp_count(search_text, 'release|deploy|deployment|rollback|canary|change advisory|cab|production incident') * 2
        + regexp_count(search_text, 'audit|compliance|sox|hipaa|soc 2|security review|change management') * 2
        + regexp_count(search_text, 'stale flag|flag debt|technical debt|owner|approver|approval') * 3
        + regexp_count(search_text, 'slack|jira|github|ci/cd|workflow|runbook')
    ) as compass_fit_score
from {{ ref('stg_web_pages') }}

