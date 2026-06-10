from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from data_ops.settings import Settings
from data_ops.snowflake import connect, qualified_name


def load_environment() -> None:
    load_dotenv()
    env_file = os.getenv("COMPASS_BACKEND_ENV_FILE", "")
    if env_file:
        load_dotenv(Path(env_file).expanduser(), override=False)


@st.cache_resource(show_spinner=False)
def snowflake_connection():
    settings = Settings.from_env()
    return connect(
        settings,
        database=settings.snowflake_database,
        schema=settings.snowflake_analytics_schema,
    )


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with snowflake_connection().cursor() as cursor:
        cursor.execute(sql, params)
        df = cursor.fetch_pandas_all()
        df.columns = [column.lower() for column in df.columns]
        return df


def analytics_table(name: str) -> str:
    settings = Settings.from_env()
    return qualified_name(settings.snowflake_database, settings.snowflake_analytics_schema, name)


def missing_snowflake_settings(settings: Settings) -> list[str]:
    values = {
        "SNOWFLAKE_ACCOUNT": settings.snowflake_account,
        "SNOWFLAKE_USER": settings.snowflake_user,
        "SNOWFLAKE_ROLE": settings.snowflake_role,
        "SNOWFLAKE_WAREHOUSE": settings.snowflake_warehouse,
        "SNOWFLAKE_DATABASE": settings.snowflake_database,
        "SNOWFLAKE_ANALYTICS_SCHEMA": settings.snowflake_analytics_schema,
        "SNOWFLAKE_STAGING_SCHEMA": settings.snowflake_staging_schema,
        "SNOWFLAKE_WEB_SCHEMA": settings.snowflake_web_schema,
    }
    missing = [key for key, value in values.items() if not value]
    if not settings.snowflake_password and not settings.snowflake_private_key_path:
        missing.append("SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH")
    return missing


def search_pages(query: str, limit: int) -> pd.DataFrame:
    table = analytics_table("MART_WEBSITE_QUERY_INDEX")
    like = f"%{query.lower()}%"
    if query.strip():
        return query_df(
            f"""
            select
                url,
                domain,
                title,
                meta_description,
                compass_fit_score,
                feature_flag_mentions,
                release_process_mentions,
                compliance_mentions,
                workflow_mentions,
                pain_mentions,
                preview_text,
                fetched_at
            from {table}
            where search_document ilike %s
            order by compass_fit_score desc, fetched_at desc
            limit %s
            """,
            (like, limit),
        )
    return query_df(
        f"""
        select
            url,
            domain,
            title,
            meta_description,
            compass_fit_score,
            feature_flag_mentions,
            release_process_mentions,
            compliance_mentions,
            workflow_mentions,
            pain_mentions,
            preview_text,
            fetched_at
        from {table}
        order by compass_fit_score desc, fetched_at desc
        limit %s
        """,
        (limit,),
    )


def load_accounts() -> pd.DataFrame:
    return query_df(
        f"""
        select
            domain,
            pages_crawled,
            feature_flag_mentions,
            release_process_mentions,
            compliance_mentions,
            workflow_mentions,
            pain_mentions,
            compass_fit_score,
            fit_tier,
            last_crawled_at
        from {analytics_table("MART_PROSPECT_ACCOUNTS")}
        order by compass_fit_score desc, pages_crawled desc
        limit 100
        """
    )


def answer_with_anthropic(question: str, pages: pd.DataFrame) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    if not api_key or not question.strip() or pages.empty:
        return None

    context_parts = []
    for row in pages.head(6).itertuples(index=False):
        context_parts.append(
            f"URL: {row.url}\nTitle: {row.title}\nText: {str(row.preview_text)[:1200]}"
        )
    prompt = (
        "Answer the question using only the website excerpts below. "
        "Call out useful prospecting, positioning, or product signals for Compass Ultra. "
        "Cite source URLs inline.\n\n"
        f"Question: {question}\n\n"
        + "\n\n---\n\n".join(context_parts)
    )
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 900,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return "\n".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")


def render_metric(label: str, value: object) -> None:
    st.markdown(f"<div class='metric'><span>{label}</span><strong>{value}</strong></div>", unsafe_allow_html=True)


def render_setup_screen(missing: list[str]) -> None:
    st.warning("The app started correctly, but Snowflake is not configured yet.")
    st.write("The desktop shortcut created `.env` from `.env.example`. Add your real Snowflake values there, then run the pipeline.")
    st.subheader("Missing Configuration")
    for key in missing:
        st.write(f"- `{key}`")
    st.subheader("Minimum `.env` Values")
    st.code(
        "\n".join(
            [
                "SNOWFLAKE_ACCOUNT=your-account-id",
                "SNOWFLAKE_USER=your-username",
                "SNOWFLAKE_PASSWORD=your-password",
                "SNOWFLAKE_ROLE=your-role",
                "SNOWFLAKE_WAREHOUSE=your-warehouse",
                "SNOWFLAKE_DATABASE=DATA_OPS",
                "SNOWFLAKE_WEB_SCHEMA=RAW_WEBSITE_INTEL",
                "SNOWFLAKE_STAGING_SCHEMA=STAGING",
                "SNOWFLAKE_ANALYTICS_SCHEMA=ANALYTICS",
            ]
        ),
        language="text",
    )
    st.subheader("After `.env` Is Filled")
    st.code(
        "\n".join(
            [
                "python scripts\\validate_environment.py",
                "python scripts\\crawl_websites_to_snowflake.py --bootstrap-only",
                "python scripts\\crawl_websites_to_snowflake.py --urls-file targets\\market_websites.txt --max-pages 25",
                "$env:DBT_PROFILES_DIR = (Get-Location).Path",
                "dbt build --select stg_web_pages fct_website_signals mart_prospect_accounts mart_website_query_index",
            ]
        ),
        language="powershell",
    )


def render_data_not_ready(error: Exception) -> None:
    st.warning("Snowflake is configured, but the website-intelligence tables are not ready yet.")
    st.write("Run the crawl and dbt build commands, then refresh this page.")
    st.code(
        "\n".join(
            [
                "python scripts\\crawl_websites_to_snowflake.py --bootstrap-only",
                "python scripts\\crawl_websites_to_snowflake.py --urls-file targets\\market_websites.txt --max-pages 25",
                "$env:DBT_PROFILES_DIR = (Get-Location).Path",
                "dbt build --select stg_web_pages fct_website_signals mart_prospect_accounts mart_website_query_index",
            ]
        ),
        language="powershell",
    )
    with st.expander("Technical detail"):
        st.code(str(error), language="text")


def main() -> None:
    load_environment()
    st.set_page_config(page_title="Compass Ultra Website Intelligence", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: #f7f4ed; color: #191a17; }
        h1, h2, h3 { letter-spacing: 0 !important; }
        .block-container { padding-top: 2rem; max-width: 1360px; }
        .metric {
          border: 1px solid #d8d1c2;
          background: #fffdf7;
          border-radius: 6px;
          padding: 14px 16px;
          min-height: 84px;
        }
        .metric span {
          display: block;
          color: #6d685f;
          font-size: .78rem;
          text-transform: uppercase;
          letter-spacing: 0 !important;
          margin-bottom: 8px;
        }
        .metric strong { font-size: 1.7rem; line-height: 1; }
        .result {
          border-top: 1px solid #d8d1c2;
          padding: 16px 0;
        }
        .result a { color: #235d53; text-decoration: none; font-weight: 700; }
        .pill {
          display: inline-block;
          border: 1px solid #c7bea9;
          border-radius: 999px;
          padding: 2px 8px;
          margin-right: 6px;
          color: #474238;
          font-size: .82rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Compass Ultra Website Intelligence")
    settings = Settings.from_env()
    missing = missing_snowflake_settings(settings)
    if missing:
        render_setup_screen(missing)
        return

    try:
        accounts = load_accounts()
    except Exception as exc:
        render_data_not_ready(exc)
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric("Domains", len(accounts))
    with col2:
        render_metric("Pages Indexed", int(accounts["pages_crawled"].sum()) if not accounts.empty else 0)
    with col3:
        render_metric("High Fit", int((accounts["fit_tier"] == "high").sum()) if not accounts.empty else 0)
    with col4:
        render_metric("Top Score", int(accounts["compass_fit_score"].max()) if not accounts.empty else 0)

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        question = st.text_input("Search", value="", placeholder="release gates, stale flags, audit-ready, LaunchDarkly")
        limit = st.slider("Results", min_value=5, max_value=50, value=15, step=5)
        results = search_pages(question, limit)
        if question and os.getenv("ANTHROPIC_API_KEY"):
            with st.spinner("Answering from retrieved pages"):
                try:
                    answer = answer_with_anthropic(question, results)
                    if answer:
                        st.markdown(answer)
                except requests.RequestException as exc:
                    st.warning(f"AI answer failed: {exc}")
        for row in results.itertuples(index=False):
            st.markdown("<div class='result'>", unsafe_allow_html=True)
            st.markdown(f"[{row.title or row.url}]({row.url})")
            st.caption(f"{row.domain} - score {row.compass_fit_score} - fetched {row.fetched_at}")
            st.markdown(
                f"<span class='pill'>flags {row.feature_flag_mentions}</span>"
                f"<span class='pill'>release {row.release_process_mentions}</span>"
                f"<span class='pill'>compliance {row.compliance_mentions}</span>"
                f"<span class='pill'>pain {row.pain_mentions}</span>",
                unsafe_allow_html=True,
            )
            st.write(str(row.preview_text)[:700])
            st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.subheader("Domains")
        st.dataframe(
            accounts,
            use_container_width=True,
            hide_index=True,
            column_config={
                "domain": "Domain",
                "pages_crawled": "Pages",
                "compass_fit_score": "Score",
                "fit_tier": "Fit",
            },
        )


if __name__ == "__main__":
    main()
