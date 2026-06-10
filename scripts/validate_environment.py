from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


REQUIRED = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_ANALYTICS_SCHEMA",
    "SNOWFLAKE_STAGING_SCHEMA",
    "SNOWFLAKE_WEB_SCHEMA",
]


def main() -> int:
    load_dotenv()
    backend_env_file = os.getenv("COMPASS_BACKEND_ENV_FILE")
    if backend_env_file:
        env_path = Path(backend_env_file).expanduser()
        if not env_path.exists():
            print(f"COMPASS_BACKEND_ENV_FILE does not exist: {backend_env_file}", file=sys.stderr)
            return 1
        load_dotenv(env_path, override=False)

    missing = [name for name in REQUIRED if not os.getenv(name)]

    authenticator = os.getenv("SNOWFLAKE_AUTHENTICATOR", "").lower()
    has_password = bool(os.getenv("SNOWFLAKE_PASSWORD"))
    private_key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    has_private_key = bool(private_key_path)
    has_browser_auth = authenticator in {"externalbrowser", "oauth", "programmatic_access_token"}

    if not has_password and not has_private_key and not has_browser_auth:
        missing.append("SNOWFLAKE_PASSWORD, SNOWFLAKE_PRIVATE_KEY_PATH, or SNOWFLAKE_AUTHENTICATOR=externalbrowser")

    if private_key_path and not Path(private_key_path).expanduser().exists():
        print(f"SNOWFLAKE_PRIVATE_KEY_PATH does not exist: {private_key_path}", file=sys.stderr)
        return 1

    if missing:
        print("Missing required configuration:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    print("Environment configuration is complete.")
    has_ai_answers = any(
        os.getenv(key)
        for key in ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"]
    )
    optional = {
        "AI sourced answers": has_ai_answers,
        "Compass Railway/Postgres ingestion": bool(os.getenv("DATABASE_URL")),
        "Stripe billing ingestion": bool(os.getenv("STRIPE_SECRET_KEY")),
        "Vercel deployment ingestion": bool(os.getenv("VERCEL_TOKEN")),
        "Fivetran metadata ingestion": bool(os.getenv("FIVETRAN_API_KEY") and os.getenv("FIVETRAN_API_SECRET")),
    }
    for label, enabled in optional.items():
        print(f"{label}: {'enabled' if enabled else 'not configured'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
