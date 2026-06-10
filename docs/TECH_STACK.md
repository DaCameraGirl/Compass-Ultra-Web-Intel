# Tech Stack

This is a data and intelligence product, so GitHub's language bar will mostly show Python. That bar does not show tools such as Snowflake, dbt, Fivetran, Stripe, Vercel, or Streamlit.

## Primary Stack

| Layer | Tool | Purpose |
| --- | --- | --- |
| Warehouse | Snowflake | Stores crawled pages and modeled analytics tables |
| Transformations | dbt Core + dbt Snowflake | Builds staging models, marts, and tests |
| Ingestion | Python | Crawls public websites and loads raw data into Snowflake |
| Query App | Streamlit | Lets Compass Ultra search and analyze website intelligence |
| Optional ELT | Fivetran API | Adds connector and destination metadata when configured |
| Optional AI | Anthropic | Produces sourced answers over retrieved website excerpts |
| Optional Product Data | Railway/Postgres, Stripe, Vercel | Adds app users, snapshots, billing, and deployments later |

## Active MVP Path

```text
Website URLs -> Python crawler -> Snowflake -> dbt marts -> Streamlit query app
```

## Future Product Data Path

```text
Compass backend + Stripe + Vercel + Fivetran -> Snowflake -> dbt marts -> operating dashboard
```

