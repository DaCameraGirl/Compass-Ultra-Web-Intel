select
    group_id,
    group_name,
    created_at,
    loaded_at
from {{ source('fivetran_api', 'GROUPS') }}

