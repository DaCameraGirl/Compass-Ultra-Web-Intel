from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    fivetran_api_key: str
    fivetran_api_secret: str
    fivetran_api_base_url: str
    snowflake_account: str
    snowflake_user: str
    snowflake_authenticator: str
    snowflake_password: str
    snowflake_private_key_path: str
    snowflake_private_key_passphrase: str
    snowflake_role: str
    snowflake_warehouse: str
    snowflake_database: str
    snowflake_raw_schema: str
    snowflake_compass_schema: str
    snowflake_stripe_schema: str
    snowflake_vercel_schema: str
    snowflake_web_schema: str
    snowflake_staging_schema: str
    snowflake_analytics_schema: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        snowflake_schema = os.getenv("SNOWFLAKE_SCHEMA", "")
        return cls(
            fivetran_api_key=os.getenv("FIVETRAN_API_KEY", ""),
            fivetran_api_secret=os.getenv("FIVETRAN_API_SECRET", ""),
            fivetran_api_base_url=os.getenv("FIVETRAN_API_BASE_URL", "https://api.fivetran.com"),
            snowflake_account=os.getenv("SNOWFLAKE_ACCOUNT", ""),
            snowflake_user=os.getenv("SNOWFLAKE_USER", ""),
            snowflake_authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", ""),
            snowflake_password=os.getenv("SNOWFLAKE_PASSWORD", ""),
            snowflake_private_key_path=os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", ""),
            snowflake_private_key_passphrase=os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", ""),
            snowflake_role=os.getenv("SNOWFLAKE_ROLE", ""),
            snowflake_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", ""),
            snowflake_database=os.getenv("SNOWFLAKE_DATABASE", "DATA_OPS"),
            snowflake_raw_schema=os.getenv("SNOWFLAKE_RAW_SCHEMA", "RAW_FIVETRAN_API"),
            snowflake_compass_schema=os.getenv("SNOWFLAKE_COMPASS_SCHEMA", "RAW_COMPASS_APP"),
            snowflake_stripe_schema=os.getenv("SNOWFLAKE_STRIPE_SCHEMA", "RAW_STRIPE"),
            snowflake_vercel_schema=os.getenv("SNOWFLAKE_VERCEL_SCHEMA", "RAW_VERCEL"),
            snowflake_web_schema=os.getenv("SNOWFLAKE_WEB_SCHEMA", "RAW_WEBSITE_INTEL"),
            snowflake_staging_schema=os.getenv("SNOWFLAKE_STAGING_SCHEMA", "STAGING"),
            snowflake_analytics_schema=os.getenv("SNOWFLAKE_ANALYTICS_SCHEMA") or snowflake_schema or "ANALYTICS",
        )
