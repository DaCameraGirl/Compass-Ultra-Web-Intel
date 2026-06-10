select
    url,
    domain,
    title,
    meta_description,
    headings,
    body_text,
    lower(concat_ws(' ', title, meta_description, to_varchar(headings), body_text)) as search_text,
    status_code,
    content_type,
    content_hash,
    fetched_at,
    length(body_text) as body_char_count
from {{ source('website_intel', 'PAGES') }}
where status_code between 200 and 299
