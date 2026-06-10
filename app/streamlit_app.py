from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from data_ops.settings import Settings
from data_ops.snowflake import connect, qualified_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPASS_FEED = Path(r"C:\Users\enter\Compass-Ultra\app\public\crawler-feed.json")
SOCIAL_AND_DIRECTORY_DOMAINS = {
    "angel.co",
    "apps.apple.com",
    "crunchbase.com",
    "facebook.com",
    "github.com",
    "instagram.com",
    "linkedin.com",
    "medium.com",
    "pitchbook.com",
    "play.google.com",
    "reddit.com",
    "twitter.com",
    "wikipedia.org",
    "x.com",
    "youtube.com",
}


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


def root_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalize_urlish(value: str) -> str:
    clean = value.strip()
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    parsed = urlparse(clean)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def looks_like_url(value: str) -> bool:
    clean = value.strip()
    first_token = clean.split()[0] if clean.split() else ""
    return clean.startswith(("http://", "https://")) or ("." in first_token and "@" not in first_token)


def result_focus_query(company_or_url: str) -> str:
    value = company_or_url.strip()
    if not value:
        return ""
    if looks_like_url(value):
        return root_domain(normalize_urlish(value)) or value
    return value


def resolve_company_source(company_or_url: str) -> tuple[str, str]:
    value = company_or_url.strip()
    if not value:
        raise ValueError("Enter a company name or website.")
    if looks_like_url(value):
        return normalize_urlish(value), "website"

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("Company-name lookup needs TAVILY_API_KEY. Enter a website URL instead.")

    response = requests.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": f"{value} official company website",
            "search_depth": "basic",
            "max_results": 8,
            "include_answer": False,
            "include_raw_content": False,
            "exclude_domains": sorted(SOCIAL_AND_DIRECTORY_DOMAINS),
        },
        timeout=45,
    )
    response.raise_for_status()
    for result in response.json().get("results", []):
        url = result.get("url")
        if not url:
            continue
        normalized = normalize_urlish(url)
        domain = root_domain(normalized)
        if domain and not any(domain == excluded or domain.endswith("." + excluded) for excluded in SOCIAL_AND_DIRECTORY_DOMAINS):
            return normalized, result.get("title") or domain
    raise RuntimeError(f"No official website found for {value}. Try entering the URL directly.")


def format_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def run_logged_command(command: list[str], env: dict[str, str], log_lines: list[str], log_box) -> None:
    log_lines.append(f"$ {format_command(command)}")
    log_box.code("\n".join(log_lines[-90:]), language="text")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip()
        if clean:
            log_lines.append(clean)
            log_box.code("\n".join(log_lines[-90:]), language="text")
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Command failed with exit code {return_code}: {format_command(command)}")


def run_company_refresh(source_url: str, max_pages: int, log_box) -> None:
    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(ROOT)
    log_lines: list[str] = []

    discover_command = [
        sys.executable,
        str(ROOT / "scripts" / "discover_websites.py"),
        "--source-url",
        source_url,
    ]
    if root_domain(source_url) == "compassultra.com" and DEFAULT_COMPASS_FEED.exists():
        discover_command.extend(["--feed-file", str(DEFAULT_COMPASS_FEED)])

    crawl_command = [
        sys.executable,
        str(ROOT / "scripts" / "crawl_websites_to_snowflake.py"),
        "--urls-file",
        "targets/discovered_websites.txt",
        "--max-pages",
        str(max_pages),
    ]

    dbt_exe = ROOT / ".venv" / "Scripts" / "dbt.exe"
    dbt_command = [
        str(dbt_exe if dbt_exe.exists() else "dbt"),
        "build",
        "--select",
        "stg_web_pages",
        "fct_website_signals",
        "mart_prospect_accounts",
        "mart_website_query_index",
    ]

    for command in [discover_command, crawl_command, dbt_command]:
        run_logged_command(command, env, log_lines, log_box)


def render_live_company_runner() -> str:
    st.markdown("<div class='live-kicker'>LIVE COMPANY RUN</div>", unsafe_allow_html=True)
    control_1, control_2, control_3 = st.columns([2.6, 0.7, 0.8])
    with control_1:
        company_or_url = st.text_input(
            "Analyze company or website",
            value=st.session_state.get("company_or_url", ""),
            placeholder="LaunchDarkly, Snowflake, https://example.com",
        )
    with control_2:
        max_pages = st.slider("Pages/site", min_value=1, max_value=25, value=5, step=1)
    with control_3:
        run_clicked = st.button("Run Analysis", type="primary", use_container_width=True)

    if not run_clicked:
        return company_or_url

    st.session_state["company_or_url"] = company_or_url
    try:
        source_url, source_label = resolve_company_source(company_or_url)
    except Exception as exc:
        st.error(str(exc))
        return company_or_url
    if not os.getenv("TAVILY_API_KEY", ""):
        st.error("Live analysis needs TAVILY_API_KEY for discovery.")
        return company_or_url

    with st.status(f"Running analysis from {root_domain(source_url)}", expanded=True) as status:
        st.write(f"Resolved source: `{source_url}`")
        st.caption(source_label)
        log_box = st.empty()
        try:
            run_company_refresh(source_url, max_pages, log_box)
        except Exception as exc:
            status.update(label="Analysis failed", state="error", expanded=True)
            st.error(str(exc))
            return company_or_url
        status.update(label="Analysis complete. Updated results are below.", state="complete", expanded=False)
    return company_or_url


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
    if (
        not settings.snowflake_password
        and not settings.snowflake_private_key_path
        and settings.snowflake_authenticator.lower() != "externalbrowser"
    ):
        missing.append("SNOWFLAKE_PASSWORD, SNOWFLAKE_PRIVATE_KEY_PATH, or SNOWFLAKE_AUTHENTICATOR=externalbrowser")
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


def answer_prompt(question: str, pages: pd.DataFrame) -> str:
    context_parts = []
    for row in pages.head(6).itertuples(index=False):
        context_parts.append(
            f"URL: {row.url}\nTitle: {row.title}\nText: {str(row.preview_text)[:1200]}"
        )
    return (
        "Answer the question using only the website excerpts below. "
        "Call out useful prospecting, positioning, or product signals for Compass Ultra. "
        "Cite source URLs inline.\n\n"
        f"Question: {question}\n\n"
        + "\n\n---\n\n".join(context_parts)
    )


def has_llm_key() -> bool:
    return any(
        os.getenv(key, "")
        for key in ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"]
    )


def openai_compatible_answer(endpoint: str, api_key: str, model: str, prompt: str, extra_headers: dict[str, str] | None = None) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    response = requests.post(
        endpoint,
        headers=headers,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 900,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("choices", [{}])[0].get("message", {}).get("content", "")


def answer_with_llm(question: str, pages: pd.DataFrame) -> str | None:
    if not question.strip() or pages.empty or not has_llm_key():
        return None

    prompt = answer_prompt(question, pages)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
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

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key:
        return openai_compatible_answer(
            "https://openrouter.ai/api/v1/chat/completions",
            api_key,
            os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat"),
            prompt,
            {"HTTP-Referer": "http://localhost:8501", "X-Title": "Compass Ultra Web Intel"},
        )

    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        return openai_compatible_answer(
            "https://api.openai.com/v1/chat/completions",
            api_key,
            os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            prompt,
        )

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if api_key:
        return openai_compatible_answer(
            "https://api.deepseek.com/chat/completions",
            api_key,
            os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            prompt,
        )
    return None


def render_metric(label: str, value: object) -> None:
    st.markdown(f"<div class='metric'><span>{label}</span><strong>{value}</strong></div>", unsafe_allow_html=True)


def render_setup_screen(missing: list[str]) -> None:
    st.warning("The app started correctly, but Snowflake is not configured yet.")
    st.write("The desktop shortcut created `.env` from `.env.example`. Add your real Snowflake values there, then run the pipeline.")
    st.subheader("Where To Get Snowflake")
    st.markdown(
        """
        - New account: [Snowflake free trial](https://signup.snowflake.com/)
        - Existing account login: [Snowflake Snowsight](https://app.snowflake.com/)
        - Account ID help: [Snowflake account identifiers](https://docs.snowflake.com/en/user-guide/admin-account-identifier)
        """
    )
    st.subheader("What To Click In Snowflake")
    st.markdown(
        """
        1. Sign in at `https://app.snowflake.com/`.
        2. Open the account selector, then choose **View account details**.
        3. Copy the account identifier for `SNOWFLAKE_ACCOUNT`. It usually looks like `orgname-accountname`.
        4. Use your login name for `SNOWFLAKE_USER`.
        5. Use `ACCOUNTADMIN` or `SYSADMIN` for `SNOWFLAKE_ROLE` if this is your own trial account.
        6. Use `COMPUTE_WH` for `SNOWFLAKE_WAREHOUSE` if you kept Snowflake's default warehouse.
        """
    )
    st.subheader("Missing Configuration")
    for key in missing:
        st.write(f"- `{key}`")
    st.subheader("Minimum `.env` Values")
    st.code(
        "\n".join(
            [
                "SNOWFLAKE_ACCOUNT=your-account-id",
                "SNOWFLAKE_USER=your-username",
                "SNOWFLAKE_AUTHENTICATOR=externalbrowser",
                "SNOWFLAKE_PASSWORD=your-password",
                "SNOWFLAKE_ROLE=your-role",
                "SNOWFLAKE_WAREHOUSE=your-warehouse",
                "SNOWFLAKE_DATABASE=DATA_OPS",
                "SNOWFLAKE_WEB_SCHEMA=RAW_WEBSITE_INTEL",
                "SNOWFLAKE_STAGING_SCHEMA=STAGING",
                "SNOWFLAKE_ANALYTICS_SCHEMA=ANALYTICS",
                "TAVILY_API_KEY=your-tavily-api-key",
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
                ".\\Run-WebsiteDiscovery.ps1 -SourceUrl https://www.compassultra.com/",
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
                ".\\Run-WebsiteDiscovery.ps1 -SourceUrl https://www.compassultra.com/",
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
        html, body, .stApp, [class*="css"], button, input, textarea {
          font-family: "Segoe UI Variable", "Segoe UI", Aptos, Calibri, sans-serif !important;
        }
        .stApp {
          background:
            linear-gradient(180deg, rgba(20, 88, 74, .10) 0, rgba(20, 88, 74, .10) 170px, transparent 171px),
            #fbfaf5;
          color: #101713;
        }
        h1 {
          color: #0f1713 !important;
          font-size: 2.55rem !important;
          font-weight: 800 !important;
          line-height: 1.08 !important;
          letter-spacing: 0 !important;
          margin-bottom: 1.1rem !important;
        }
        h2, h3 {
          color: #122019 !important;
          letter-spacing: 0 !important;
        }
        label, p, span, div {
          color: #17241d;
        }
        .block-container {
          padding-top: 3rem;
          padding-bottom: 3.5rem;
          max-width: 1220px;
        }
        [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] {
          gap: .85rem;
        }
        [data-testid="stHorizontalBlock"] {
          gap: 1rem;
        }
        [data-testid="stTextInput"] input {
          background: #ffffff !important;
          color: #101713 !important;
          border: 1px solid #c7d1c9 !important;
          border-radius: 7px !important;
          min-height: 44px;
        }
        [data-testid="stTextInput"] input:focus {
          border-color: #14584a !important;
          box-shadow: 0 0 0 1px #14584a !important;
        }
        [data-testid="stSlider"] {
          padding-top: 0;
        }
        .stButton > button {
          min-height: 43px;
          border-radius: 7px !important;
          border: 1px solid #14584a !important;
          background: #14584a !important;
          color: #ffffff !important;
          font-weight: 800 !important;
        }
        .stButton > button:hover {
          background: #0f473c !important;
          border-color: #0f473c !important;
          color: #ffffff !important;
        }
        .metric {
          border: 1px solid #d0d9d1;
          background: #ffffff;
          border-radius: 7px;
          padding: 16px 18px;
          min-height: 88px;
          box-shadow: 0 8px 18px rgba(20, 45, 34, .05);
        }
        .metric span {
          display: block;
          color: #536157;
          font-size: .78rem;
          text-transform: uppercase;
          letter-spacing: 0 !important;
          margin-bottom: 8px;
          font-weight: 750;
        }
        .metric strong {
          color: #0f1713;
          font-size: 1.75rem;
          line-height: 1;
        }
        .live-kicker {
          display: inline-flex;
          align-items: center;
          border: 1px solid #255d52;
          border-radius: 7px;
          color: #ffffff;
          background: #14584a;
          font-size: .76rem;
          font-weight: 800;
          letter-spacing: .04em;
          padding: 5px 9px;
          margin: 2px 0 10px;
        }
        .focus-note {
          color: #526158;
          font-size: .9rem;
          margin: 4px 0 12px;
        }
        .result {
          border-top: 1px solid #d3ddd5;
          padding: 18px 0;
          background: transparent;
        }
        .result a {
          color: #14584a;
          text-decoration: none;
          font-weight: 800;
        }
        .result p {
          color: #26362d;
          font-size: .98rem;
          line-height: 1.58;
        }
        .pill {
          display: inline-block;
          border: 1px solid #b9c8be;
          background: #ffffff;
          border-radius: 999px;
          padding: 3px 9px;
          margin-right: 6px;
          color: #26362d;
          font-size: .82rem;
          font-weight: 650;
        }
        [data-testid="stDataFrame"] {
          border: 1px solid #d0d9d1;
          border-radius: 7px;
          overflow: hidden;
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

    company_or_url = render_live_company_runner()
    focus_query = result_focus_query(company_or_url)

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
        limit = st.slider("Results", min_value=5, max_value=50, value=15, step=5)
        if focus_query:
            st.markdown(f"<div class='focus-note'>Showing matches for <strong>{focus_query}</strong></div>", unsafe_allow_html=True)
        results = search_pages(focus_query, limit)
        if focus_query and has_llm_key():
            with st.spinner("Answering from retrieved pages"):
                try:
                    answer = answer_with_llm(f"Summarize the strongest website intelligence signals for {focus_query}.", results)
                    if answer:
                        st.markdown(answer)
                except Exception as exc:
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
