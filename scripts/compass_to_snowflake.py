from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_ops.settings import Settings
from data_ops.snowflake import connect, qualified_name, quote_ident


TYPE_CASTS = {
    "varchar": "{name}",
    "boolean": "try_to_boolean({name})",
    "number": "try_to_number({name})",
    "timestamp_tz": "try_to_timestamp_tz({name})",
    "variant": "parse_json({name})",
}


def load_environment() -> None:
    load_dotenv()
    env_file = os.getenv("COMPASS_BACKEND_ENV_FILE", "")
    if env_file:
        load_dotenv(Path(env_file).expanduser(), override=False)


def serialize(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=serialize, sort_keys=True)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def unix_time(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def create_raw_objects(connection, settings: Settings) -> None:
    db = settings.snowflake_database
    schemas = [
        settings.snowflake_compass_schema,
        settings.snowflake_stripe_schema,
        settings.snowflake_vercel_schema,
    ]
    statements = [f"create database if not exists {quote_ident(db)}"]
    statements.extend(f"create schema if not exists {qualified_name(db, schema)}" for schema in schemas)
    statements.extend(
        [
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_compass_schema, 'USERS')} (
                user_id varchar not null,
                auth0_id varchar not null,
                email varchar,
                name varchar,
                plan varchar,
                signup_source varchar,
                company varchar,
                role_title varchar,
                team_size varchar,
                primary_provider varchar,
                stripe_customer_id varchar,
                signup_completed_at timestamp_tz,
                last_seen_at timestamp_tz,
                updated_at timestamp_tz,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (user_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_compass_schema, 'SIGNUP_EVENTS')} (
                signup_event_id varchar not null,
                user_id varchar,
                auth0_id varchar,
                email varchar,
                event_type varchar,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                details variant,
                raw_payload variant not null,
                primary key (signup_event_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_compass_schema, 'SNAPSHOTS')} (
                snapshot_id varchar not null,
                user_id varchar not null,
                name varchar,
                description varchar,
                is_public boolean,
                created_at timestamp_tz,
                updated_at timestamp_tz,
                loaded_at timestamp_tz not null,
                snapshot_data variant not null,
                raw_payload variant not null,
                primary key (snapshot_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_compass_schema, 'AUDIT_LOG')} (
                audit_id varchar not null,
                user_id varchar,
                auth0_id varchar,
                email varchar,
                action varchar,
                resource_type varchar,
                resource_id varchar,
                success boolean,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                details variant,
                raw_payload variant not null,
                primary key (audit_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_stripe_schema, 'CUSTOMERS')} (
                customer_id varchar not null,
                email varchar,
                name varchar,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (customer_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_stripe_schema, 'SUBSCRIPTIONS')} (
                subscription_id varchar not null,
                customer_id varchar,
                status varchar,
                price_id varchar,
                amount_cents number,
                currency varchar,
                interval varchar,
                metadata_user_id varchar,
                metadata_plan varchar,
                current_period_start timestamp_tz,
                current_period_end timestamp_tz,
                trial_start timestamp_tz,
                trial_end timestamp_tz,
                canceled_at timestamp_tz,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (subscription_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_stripe_schema, 'CHECKOUT_SESSIONS')} (
                session_id varchar not null,
                customer_id varchar,
                subscription_id varchar,
                status varchar,
                payment_status varchar,
                customer_email varchar,
                metadata_user_id varchar,
                metadata_plan varchar,
                created_at timestamp_tz,
                loaded_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (session_id)
            )
            """,
            f"""
            create table if not exists {qualified_name(db, settings.snowflake_vercel_schema, 'DEPLOYMENTS')} (
                deployment_id varchar not null,
                project_id varchar,
                name varchar,
                url varchar,
                target varchar,
                state varchar,
                ready_state varchar,
                creator_email varchar,
                git_branch varchar,
                git_sha varchar,
                created_at timestamp_tz,
                ready_at timestamp_tz,
                loaded_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (deployment_id)
            )
            """,
        ]
    )
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        cursor.execute(f"use database {quote_ident(db)}")
        cursor.execute(f"use schema {qualified_name(db, settings.snowflake_compass_schema)}")


def merge_rows(
    connection,
    table_name: str,
    key_column: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    temp_table = f"TMP_{key_column.upper()}_{uuid.uuid4().hex[:10].upper()}"
    column_names = [column for column, _ in columns]
    temp_defs = ", ".join(f"{quote_ident(column)} varchar" for column in column_names)
    insert_cols = ", ".join(quote_ident(column) for column in column_names)
    placeholders = ", ".join(["%s"] * len(column_names))
    source_select = ", ".join(
        f"{TYPE_CASTS[column_type].format(name=quote_ident(column))} as {quote_ident(column)}"
        for column, column_type in columns
    )
    update_set = ", ".join(
        f"target.{quote_ident(column)} = source.{quote_ident(column)}"
        for column in column_names
        if column != key_column
    )
    insert_values = ", ".join(f"source.{quote_ident(column)}" for column in column_names)
    values = [tuple(serialize(row.get(column)) for column in column_names) for row in rows]

    with connection.cursor() as cursor:
        cursor.execute(f"create temporary table {quote_ident(temp_table)} ({temp_defs})")
        cursor.executemany(
            f"insert into {quote_ident(temp_table)} ({insert_cols}) values ({placeholders})",
            values,
        )
        cursor.execute(
            f"""
            merge into {table_name} as target
            using (select {source_select} from {quote_ident(temp_table)}) as source
            on target.{quote_ident(key_column)} = source.{quote_ident(key_column)}
            when matched then update set {update_set}
            when not matched then insert ({insert_cols})
            values ({insert_values})
            """
        )


def fetch_postgres_rows(database_url: str, query: str) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as pg_connection:
        with pg_connection.cursor() as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())


def load_compass_backend(connection, settings: Settings) -> dict[str, int]:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        return {"users": 0, "signup_events": 0, "snapshots": 0, "audit_log": 0}

    loaded_at = datetime.now(timezone.utc)
    db = settings.snowflake_database
    schema = settings.snowflake_compass_schema

    users = fetch_postgres_rows(
        database_url,
        """
        select id, auth0_id, email, name, plan, signup_source, company, role_title, team_size,
               primary_provider, stripe_customer_id, signup_completed_at, last_seen_at,
               updated_at, created_at, row_to_json(users.*) as raw_payload
        from users
        """,
    )
    for row in users:
        row["user_id"] = row.pop("id")
        row["loaded_at"] = loaded_at

    signup_events = fetch_postgres_rows(
        database_url,
        """
        select id, user_id, auth0_id, email, event_type, created_at, details,
               row_to_json(signup_events.*) as raw_payload
        from signup_events
        """,
    )
    for row in signup_events:
        row["signup_event_id"] = row.pop("id")
        row["loaded_at"] = loaded_at

    snapshots = fetch_postgres_rows(
        database_url,
        """
        select id, user_id, name, description, snapshot_data, is_public, created_at, updated_at,
               row_to_json(snapshots.*) as raw_payload
        from snapshots
        """,
    )
    for row in snapshots:
        row["snapshot_id"] = row.pop("id")
        row["loaded_at"] = loaded_at

    audit_log = fetch_postgres_rows(
        database_url,
        """
        select id, user_id, auth0_id, email, action, resource_type, resource_id, details,
               success, created_at, row_to_json(audit_log.*) as raw_payload
        from audit_log
        """,
    )
    for row in audit_log:
        row["audit_id"] = row.pop("id")
        row["loaded_at"] = loaded_at

    merge_rows(
        connection,
        qualified_name(db, schema, "USERS"),
        "user_id",
        [
            ("user_id", "varchar"),
            ("auth0_id", "varchar"),
            ("email", "varchar"),
            ("name", "varchar"),
            ("plan", "varchar"),
            ("signup_source", "varchar"),
            ("company", "varchar"),
            ("role_title", "varchar"),
            ("team_size", "varchar"),
            ("primary_provider", "varchar"),
            ("stripe_customer_id", "varchar"),
            ("signup_completed_at", "timestamp_tz"),
            ("last_seen_at", "timestamp_tz"),
            ("updated_at", "timestamp_tz"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("raw_payload", "variant"),
        ],
        users,
    )
    merge_rows(
        connection,
        qualified_name(db, schema, "SIGNUP_EVENTS"),
        "signup_event_id",
        [
            ("signup_event_id", "varchar"),
            ("user_id", "varchar"),
            ("auth0_id", "varchar"),
            ("email", "varchar"),
            ("event_type", "varchar"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("details", "variant"),
            ("raw_payload", "variant"),
        ],
        signup_events,
    )
    merge_rows(
        connection,
        qualified_name(db, schema, "SNAPSHOTS"),
        "snapshot_id",
        [
            ("snapshot_id", "varchar"),
            ("user_id", "varchar"),
            ("name", "varchar"),
            ("description", "varchar"),
            ("is_public", "boolean"),
            ("created_at", "timestamp_tz"),
            ("updated_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("snapshot_data", "variant"),
            ("raw_payload", "variant"),
        ],
        snapshots,
    )
    merge_rows(
        connection,
        qualified_name(db, schema, "AUDIT_LOG"),
        "audit_id",
        [
            ("audit_id", "varchar"),
            ("user_id", "varchar"),
            ("auth0_id", "varchar"),
            ("email", "varchar"),
            ("action", "varchar"),
            ("resource_type", "varchar"),
            ("resource_id", "varchar"),
            ("success", "boolean"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("details", "variant"),
            ("raw_payload", "variant"),
        ],
        audit_log,
    )
    return {
        "users": len(users),
        "signup_events": len(signup_events),
        "snapshots": len(snapshots),
        "audit_log": len(audit_log),
    }


def stripe_list(endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    secret_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret_key:
        return []
    items: list[dict[str, Any]] = []
    starting_after: str | None = None
    while True:
        page_params = {"limit": 100, **(params or {})}
        if starting_after:
            page_params["starting_after"] = starting_after
        response = requests.get(
            f"https://api.stripe.com/v1/{endpoint}",
            auth=(secret_key, ""),
            params=page_params,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        items.extend(data)
        if not payload.get("has_more") or not data:
            return items
        starting_after = data[-1]["id"]


def load_stripe(connection, settings: Settings) -> dict[str, int]:
    if not os.getenv("STRIPE_SECRET_KEY"):
        return {"customers": 0, "subscriptions": 0, "checkout_sessions": 0}

    loaded_at = datetime.now(timezone.utc)
    customers = []
    for item in stripe_list("customers"):
        customers.append(
            {
                "customer_id": item["id"],
                "email": item.get("email"),
                "name": item.get("name"),
                "created_at": unix_time(item.get("created")),
                "loaded_at": loaded_at,
                "raw_payload": item,
            }
        )

    subscriptions = []
    for item in stripe_list("subscriptions", {"status": "all"}):
        price = (item.get("items", {}).get("data") or [{}])[0].get("price") or {}
        metadata = item.get("metadata") or {}
        subscriptions.append(
            {
                "subscription_id": item["id"],
                "customer_id": item.get("customer"),
                "status": item.get("status"),
                "price_id": price.get("id"),
                "amount_cents": price.get("unit_amount"),
                "currency": price.get("currency"),
                "interval": (price.get("recurring") or {}).get("interval"),
                "metadata_user_id": metadata.get("userId"),
                "metadata_plan": metadata.get("plan"),
                "current_period_start": unix_time(item.get("current_period_start")),
                "current_period_end": unix_time(item.get("current_period_end")),
                "trial_start": unix_time(item.get("trial_start")),
                "trial_end": unix_time(item.get("trial_end")),
                "canceled_at": unix_time(item.get("canceled_at")),
                "created_at": unix_time(item.get("created")),
                "loaded_at": loaded_at,
                "raw_payload": item,
            }
        )

    checkout_sessions = []
    for item in stripe_list("checkout/sessions"):
        metadata = item.get("metadata") or {}
        checkout_sessions.append(
            {
                "session_id": item["id"],
                "customer_id": item.get("customer"),
                "subscription_id": item.get("subscription"),
                "status": item.get("status"),
                "payment_status": item.get("payment_status"),
                "customer_email": item.get("customer_email") or (item.get("customer_details") or {}).get("email"),
                "metadata_user_id": metadata.get("userId"),
                "metadata_plan": metadata.get("plan"),
                "created_at": unix_time(item.get("created")),
                "loaded_at": loaded_at,
                "raw_payload": item,
            }
        )

    db = settings.snowflake_database
    schema = settings.snowflake_stripe_schema
    merge_rows(
        connection,
        qualified_name(db, schema, "CUSTOMERS"),
        "customer_id",
        [
            ("customer_id", "varchar"),
            ("email", "varchar"),
            ("name", "varchar"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("raw_payload", "variant"),
        ],
        customers,
    )
    merge_rows(
        connection,
        qualified_name(db, schema, "SUBSCRIPTIONS"),
        "subscription_id",
        [
            ("subscription_id", "varchar"),
            ("customer_id", "varchar"),
            ("status", "varchar"),
            ("price_id", "varchar"),
            ("amount_cents", "number"),
            ("currency", "varchar"),
            ("interval", "varchar"),
            ("metadata_user_id", "varchar"),
            ("metadata_plan", "varchar"),
            ("current_period_start", "timestamp_tz"),
            ("current_period_end", "timestamp_tz"),
            ("trial_start", "timestamp_tz"),
            ("trial_end", "timestamp_tz"),
            ("canceled_at", "timestamp_tz"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("raw_payload", "variant"),
        ],
        subscriptions,
    )
    merge_rows(
        connection,
        qualified_name(db, schema, "CHECKOUT_SESSIONS"),
        "session_id",
        [
            ("session_id", "varchar"),
            ("customer_id", "varchar"),
            ("subscription_id", "varchar"),
            ("status", "varchar"),
            ("payment_status", "varchar"),
            ("customer_email", "varchar"),
            ("metadata_user_id", "varchar"),
            ("metadata_plan", "varchar"),
            ("created_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("raw_payload", "variant"),
        ],
        checkout_sessions,
    )
    return {
        "customers": len(customers),
        "subscriptions": len(subscriptions),
        "checkout_sessions": len(checkout_sessions),
    }


def load_vercel(connection, settings: Settings) -> dict[str, int]:
    token = os.getenv("VERCEL_TOKEN", "")
    if not token:
        return {"deployments": 0}

    params: dict[str, Any] = {"limit": 100}
    for env_name, query_name in {
        "VERCEL_PROJECT_ID": "projectId",
        "VERCEL_TEAM_ID": "teamId",
        "VERCEL_TEAM_SLUG": "slug",
    }.items():
        value = os.getenv(env_name)
        if value:
            params[query_name] = value

    deployments: list[dict[str, Any]] = []
    until = None
    while True:
        page_params = dict(params)
        if until:
            page_params["until"] = until
        response = requests.get(
            "https://api.vercel.com/v6/deployments",
            headers={"Authorization": f"Bearer {token}"},
            params=page_params,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("deployments", [])
        deployments.extend(page)
        until = (payload.get("pagination") or {}).get("next")
        if not until or not page:
            break

    loaded_at = datetime.now(timezone.utc)
    rows = []
    for item in deployments:
        meta = item.get("meta") or {}
        creator = item.get("creator") or {}
        rows.append(
            {
                "deployment_id": item["uid"],
                "project_id": item.get("projectId"),
                "name": item.get("name"),
                "url": item.get("url"),
                "target": item.get("target"),
                "state": item.get("state"),
                "ready_state": item.get("readyState"),
                "creator_email": creator.get("email"),
                "git_branch": meta.get("githubCommitRef") or meta.get("gitlabCommitRef") or meta.get("bitbucketCommitRef"),
                "git_sha": meta.get("githubCommitSha") or meta.get("gitlabCommitSha") or meta.get("bitbucketCommitSha"),
                "created_at": unix_time(int(item["createdAt"] / 1000)) if item.get("createdAt") else None,
                "ready_at": unix_time(int(item["ready"] / 1000)) if item.get("ready") else None,
                "loaded_at": loaded_at,
                "raw_payload": item,
            }
        )

    merge_rows(
        connection,
        qualified_name(settings.snowflake_database, settings.snowflake_vercel_schema, "DEPLOYMENTS"),
        "deployment_id",
        [
            ("deployment_id", "varchar"),
            ("project_id", "varchar"),
            ("name", "varchar"),
            ("url", "varchar"),
            ("target", "varchar"),
            ("state", "varchar"),
            ("ready_state", "varchar"),
            ("creator_email", "varchar"),
            ("git_branch", "varchar"),
            ("git_sha", "varchar"),
            ("created_at", "timestamp_tz"),
            ("ready_at", "timestamp_tz"),
            ("loaded_at", "timestamp_tz"),
            ("raw_payload", "variant"),
        ],
        rows,
    )
    return {"deployments": len(rows)}


def require_snowflake(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "SNOWFLAKE_ACCOUNT": settings.snowflake_account,
            "SNOWFLAKE_USER": settings.snowflake_user,
            "SNOWFLAKE_ROLE": settings.snowflake_role,
            "SNOWFLAKE_WAREHOUSE": settings.snowflake_warehouse,
        }.items()
        if not value
    ]
    if (
        not settings.snowflake_password
        and not settings.snowflake_private_key_path
        and settings.snowflake_authenticator.lower() != "externalbrowser"
    ):
        missing.append("SNOWFLAKE_PASSWORD, SNOWFLAKE_PRIVATE_KEY_PATH, or SNOWFLAKE_AUTHENTICATOR=externalbrowser")
    if missing:
        raise RuntimeError("Missing required Snowflake configuration: " + ", ".join(missing))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Load Compass Ultra operating data into Snowflake.")
    parser.add_argument("--bootstrap-only", action="store_true", help="Create raw Snowflake tables and exit.")
    args = parser.parse_args(argv)

    load_environment()
    settings = Settings.from_env()
    require_snowflake(settings)

    with connect(settings) as snowflake_connection:
        create_raw_objects(snowflake_connection, settings)
        if args.bootstrap_only:
            print("Compass Ultra raw Snowflake objects are ready.")
            return 0

        counts = {
            "compass_backend": load_compass_backend(snowflake_connection, settings),
            "stripe": load_stripe(snowflake_connection, settings),
            "vercel": load_vercel(snowflake_connection, settings),
        }
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
