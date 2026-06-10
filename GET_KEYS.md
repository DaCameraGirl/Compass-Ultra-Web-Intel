# Accounts And Keys You Need

The website-intelligence workflow only needs Snowflake. Other API keys are optional.

## 1. Snowflake Required

Go to:

https://signup.snowflake.com/

If you already have an account, sign in here:

https://app.snowflake.com/

Create a trial account or sign in. In Snowflake, collect these values:

- account identifier
- username
- password or private key
- role
- warehouse

Where to find the account identifier:

1. Sign in to Snowsight.
2. Open the account selector.
3. Select **View account details**.
4. Copy the account identifier. Snowflake documents this flow here:

https://docs.snowflake.com/en/user-guide/admin-account-identifier

For a new personal trial, common starting values are:

```text
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
```

The Snowflake role needs access to:

- your project database
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`

The website crawler stores public pages in Snowflake and dbt builds the query tables.

## 2. Anthropic Optional

Use this only if you want AI answers over crawled websites.

https://console.anthropic.com/

Create an API key and set:

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`

The default model in `.env.example` is `claude-sonnet-4-6`.

## 3. Fivetran Optional

Use this later if you want managed connectors into Snowflake.

https://www.fivetran.com/signup

Create a Fivetran API key and secret in Fivetran account or user settings.

## 4. Vercel Optional

Use this later if you want deployment data in the warehouse.

https://vercel.com/account/tokens

Create a token and set:

- `VERCEL_TOKEN`
- `VERCEL_PROJECT_ID`

## 5. Existing Compass Backend Secrets

Your Compass backend already has useful values like `DATABASE_URL`, `STRIPE_SECRET_KEY`, and `ANTHROPIC_API_KEY`.

Do not copy them into chat. Point this repo to that local file:

```text
COMPASS_BACKEND_ENV_FILE=C:\Users\enter\Compass-Ultra-Backend\.env
```

## 6. dbt

No dbt Cloud account is required. This project uses dbt Core from `requirements.txt`.

Never paste API keys into chat and never commit `.env`.
