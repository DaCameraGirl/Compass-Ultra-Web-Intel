# Compass Ultra Website Intelligence

![Snowflake](https://img.shields.io/badge/Snowflake-Data%20Warehouse-29B5E8)
![dbt](https://img.shields.io/badge/dbt-Transformations-FF694B)
![Fivetran Ready](https://img.shields.io/badge/Fivetran-Ready%20Ingestion-1D4ED8)
![Streamlit](https://img.shields.io/badge/Streamlit-Query%20App-FF4B4B)
![Compass Ultra](https://img.shields.io/badge/Compass%20Ultra-Website%20Intelligence-235D53)

Compass Ultra Website Intelligence is a Snowflake + dbt + Streamlit pipeline for Compass Ultra's early-stage growth work: pull public website data, model it, and query it for market, competitor, and prospect signals before there are customers.

The core workflow does not need Stripe, Auth0, Railway, Vercel, or Fivetran. Those integrations are wired as optional sources for later.

## Stack

- **Snowflake**: warehouse for crawled website pages, optional Compass backend data, optional Stripe/Vercel data, and optional Fivetran metadata
- **dbt Core + dbt Snowflake**: staging models, marts, tests, and query-ready analytics tables
- **Fivetran-ready ingestion**: Fivetran API metadata loader is included for connector health and destination visibility
- **Python**: website crawler, API ingestion jobs, Snowflake loading, validation scripts
- **Streamlit**: local query app for website intelligence and prospect/domain scoring
- **Anthropic optional**: sourced answers over retrieved website pages when `ANTHROPIC_API_KEY` is configured

## Architecture

```text
Public websites
  -> Python crawler
  -> Snowflake RAW_WEBSITE_INTEL.PAGES
  -> dbt staging and marts
  -> Streamlit query app

Optional later sources
  -> Fivetran API metadata
  -> Compass Ultra Railway/Postgres backend
  -> Stripe billing objects
  -> Vercel deployment history
  -> Snowflake + dbt analytics marts
```

## What It Does Now

- Crawls real websites from `targets/market_websites.txt` or URLs you pass on the command line
- Extracts titles, descriptions, headings, visible text, links, and crawl metadata
- Loads pages into Snowflake under `RAW_WEBSITE_INTEL`
- Uses dbt to build a website query index, domain scorecard, and Compass-fit signal tables
- Runs a Streamlit query app over the dbt marts
- Uses Anthropic for sourced answers when `ANTHROPIC_API_KEY` is configured

## Core Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` with real Snowflake values. Do not commit `.env`.

Validate:

```powershell
python scripts\validate_environment.py
```

Create the raw website table:

```powershell
python scripts\crawl_websites_to_snowflake.py --bootstrap-only
```

Crawl real websites into Snowflake:

```powershell
python scripts\crawl_websites_to_snowflake.py --urls-file targets\market_websites.txt --max-pages 25
```

Build the dbt website marts:

```powershell
$env:DBT_PROFILES_DIR = (Get-Location).Path
dbt build --select stg_web_pages fct_website_signals mart_prospect_accounts mart_website_query_index
```

Run the query app:

```powershell
streamlit run app\streamlit_app.py
```

On Windows, double-click the desktop shortcut named **Compass Ultra Web Intel** if it has been created. It runs `Start-CompassUltraWebIntel.ps1`.

The first shortcut launch creates `.env` and installs dependencies. If `.env` is still blank, the app opens to a setup checklist instead of trying to connect to Snowflake. The repo includes `.streamlit/config.toml` to keep Streamlit's built-in toolbar minimal for local use.

## Useful Queries

Search the app for:

- `release gates`
- `stale flags`
- `audit-ready`
- `LaunchDarkly`
- `rollback`
- `change advisory`
- `feature flag debt`

The app ranks pages and domains by Compass Ultra fit signals.

## Optional Sources

These are not required for the website-intelligence workflow.

- `scripts\compass_to_snowflake.py`: loads Compass Ultra backend data from Railway/Postgres, Stripe billing, and Vercel deployments when those credentials are configured.
- `scripts\fivetran_to_snowflake.py`: loads Fivetran group/connection metadata when Fivetran API credentials are configured.

If your Compass backend `.env` already has `DATABASE_URL`, `STRIPE_SECRET_KEY`, or `ANTHROPIC_API_KEY`, set this in this repo's `.env` instead of copying secrets:

```text
COMPASS_BACKEND_ENV_FILE=C:\Users\enter\Compass-Ultra-Backend\.env
```

The scripts read values locally and never print secret values.

## dbt Outputs

- `ANALYTICS.MART_WEBSITE_QUERY_INDEX`
- `ANALYTICS.MART_PROSPECT_ACCOUNTS`
- `ANALYTICS.FCT_WEBSITE_SIGNALS`

Optional operational marts are present for future customer/billing/deployment analysis, but the active MVP is website intelligence.

## Store Packaging

Store-wrapper scaffolding lives in `store/`.

- Android and iOS: `store/capacitor`
- PWA manifest: `store/pwa/manifest.webmanifest`
- Microsoft Store notes: `store/microsoft`

Before a real store submission, host the app at a production HTTPS URL and set `COMPASS_WEB_INTEL_URL` for the Capacitor wrapper. Store submissions also require developer accounts, signing certificates, screenshots, privacy labels, and production icons.

## More Detail

See [docs/TECH_STACK.md](docs/TECH_STACK.md) for how GitHub language detection differs from the actual product stack.
