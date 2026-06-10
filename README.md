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
- **Optional LLM answers**: sourced answers over retrieved website pages with Anthropic, OpenAI, OpenRouter, or DeepSeek keys

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

- Discovers related websites from a source site/feed using Tavily Search
- Crawls discovered websites or URLs you pass on the command line
- Extracts titles, descriptions, headings, visible text, links, and crawl metadata
- Loads pages into Snowflake under `RAW_WEBSITE_INTEL`
- Uses dbt to build a website query index, domain scorecard, and Compass-fit signal tables
- Runs a Streamlit query app over the dbt marts
- Uses Anthropic, OpenAI, OpenRouter, or DeepSeek for sourced answers when a supported LLM key is configured

## Core Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` with real Snowflake values. Do not commit `.env`.

Get Snowflake here:

- New trial: https://signup.snowflake.com/
- Login: https://app.snowflake.com/
- Account ID help: https://docs.snowflake.com/en/user-guide/admin-account-identifier

Validate:

```powershell
python scripts\validate_environment.py
```

Create the raw website table:

```powershell
python scripts\crawl_websites_to_snowflake.py --bootstrap-only
```

Discover related websites from a source website:

```powershell
python scripts\discover_websites.py --source-url https://www.example.com/
```

Crawl discovered websites into Snowflake:

```powershell
python scripts\crawl_websites_to_snowflake.py --urls-file targets\discovered_websites.txt --max-pages 25
```

Load a crawler-safe JSON feed when a site blocks normal crawlers:

```powershell
python scripts\crawl_websites_to_snowflake.py --feed-file C:\path\to\crawler-feed.json --skip-urls-file
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

In the app, enter a company name or website in **Company or website**, then click **Run Analysis**. `TAVILY_API_KEY` is required for live discovery; direct website URLs only skip the company-name lookup step.

The first shortcut launch creates `.env` and installs dependencies. If `.env` is still blank, the app opens to a setup checklist instead of trying to connect to Snowflake. The repo includes `.streamlit/config.toml` to keep Streamlit's built-in toolbar minimal for local use.

If Snowflake browser login is not enabled for the account, run `Set-SnowflakePassword.ps1` locally. It prompts for the Snowflake password and writes it only to `.env`.

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

If your Compass backend `.env` already has `DATABASE_URL`, `STRIPE_SECRET_KEY`, or AI provider keys, set this in this repo's `.env` instead of copying secrets:

```text
COMPASS_BACKEND_ENV_FILE=C:\Users\enter\Compass-Ultra-Backend\.env
```

The scripts read values locally and never print secret values.

## One-Command Discovery Refresh

On Windows, run:

```powershell
.\Run-WebsiteDiscovery.ps1
```

That discovers related websites from Compass Ultra by default, crawls them, loads Snowflake, rebuilds dbt, and opens the local app. To run another source website:

```powershell
.\Run-WebsiteDiscovery.ps1 -SourceUrl https://www.example.com/ -MaxPages 5
```

## Hosting

This app needs a Python/Streamlit runtime, Snowflake credentials, and Tavily for live discovery. GitHub Pages is not enough because it only serves static files.

Use Streamlit Community Cloud for a free public deployment from the GitHub repo. Put secrets in Streamlit's secrets manager, not in GitHub:

- `TAVILY_API_KEY`
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_PASSWORD` or key-pair settings
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- optional AI provider keys

Before sharing the app publicly, add access control or disable unrestricted live runs so visitors cannot trigger crawl/Snowflake/API usage without permission.

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
