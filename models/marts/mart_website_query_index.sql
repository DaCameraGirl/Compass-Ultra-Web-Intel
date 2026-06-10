select
    p.url,
    p.domain,
    p.title,
    p.meta_description,
    p.fetched_at,
    s.feature_flag_mentions,
    s.release_process_mentions,
    s.compliance_mentions,
    s.workflow_mentions,
    s.pain_mentions,
    s.compass_fit_score,
    left(p.body_text, 1200) as preview_text,
    left(p.search_text, 12000) as search_document
from {{ ref('stg_web_pages') }} as p
left join {{ ref('fct_website_signals') }} as s
    on p.url = s.url
