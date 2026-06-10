# Compass Ultra Website Intelligence

This repo is a real Snowflake + dbt + app pipeline for Compass Ultra’s early-stage need: pull public website data, model it, and query it for market, competitor, and prospect signals before there are customers.

The core workflow does not need Stripe, Auth0, Railway, Vercel, or Fivetran. Those integrations are wired as optional sources for later.

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

If your Compass backend `.env` already has `DATABASE_URL`, `STRIPE_SECRET_KEY`, or `ANTHROPIC_API_KEY`, set this in this repo’s `.env` instead of copying secrets:

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
