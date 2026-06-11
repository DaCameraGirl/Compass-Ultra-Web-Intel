# Streamlit Cloud Runbook

Compass Ultra Website Intelligence runs on Streamlit Cloud from:

```text
app/streamlit_app.py
```

GitHub Pages is only the static portfolio page. Streamlit Cloud is the runtime for the live Python app.

## Required Secrets

Add secrets in Streamlit Cloud:

```text
Manage app -> Settings -> Secrets
```

Use TOML format:

```toml
COMPASS_PUBLIC_MODE = "true"
COMPASS_ACCESS_CODE = "choose-a-private-code"
COMPASS_LIVE_RUNS_ENABLED = "true"
COMPASS_MAX_PAGES_PER_RUN = "5"
COMPASS_RUN_COOLDOWN_SECONDS = "300"

TAVILY_API_KEY = "..."

SNOWFLAKE_ACCOUNT = "..."
SNOWFLAKE_USER = "..."
SNOWFLAKE_PASSWORD = "..."
SNOWFLAKE_ROLE = "..."
SNOWFLAKE_WAREHOUSE = "..."
SNOWFLAKE_DATABASE = "DATA_OPS"
SNOWFLAKE_WEB_SCHEMA = "RAW_WEBSITE_INTEL"
SNOWFLAKE_STAGING_SCHEMA = "STAGING"
SNOWFLAKE_ANALYTICS_SCHEMA = "ANALYTICS"
```

Do not commit `.env`, `.streamlit/secrets.toml`, local key inventories, API keys, tokens, passwords, or private credentials.

## Deployment Flow

1. Commit focused changes locally.
2. Fetch or pull/rebase `origin main`.
3. Push `main`.
4. Let Streamlit Cloud redeploy, or use **Manage app -> Reboot app**.
5. Unlock with the configured `COMPASS_ACCESS_CODE`.
6. Confirm the live button reads **Run Analysis**.

## Verification

Before pushing app changes, run:

```powershell
.\.venv\Scripts\python.exe -m py_compile app\streamlit_app.py data_ops\settings.py
git diff --check
```

For guarded UI changes, use Streamlit AppTest for public and unlocked states.

## Source Resolution Behavior

When a user enters a URL, the app runs that URL directly.

When a user enters a company name, the app asks Tavily for the official website and scores candidates by:

- exact or close domain match,
- homepage preference,
- company-name terms in the domain/title,
- exclusion of social, app-store, and directory domains.

Low-confidence matches require confirmation before crawling. This prevents searches like `compass ultra` from automatically running an unrelated content page such as a luxury real estate article.
