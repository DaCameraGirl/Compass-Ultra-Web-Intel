from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_ops.settings import Settings
from data_ops.snowflake import connect, qualified_name, quote_ident


class FivetranClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.fivetran_api_base_url.rstrip("/")
        self.auth = (settings.fivetran_api_key, settings.fivetran_api_secret)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(5):
            response = self.session.get(url, auth=self.auth, params=params, timeout=60)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                continue
            if 500 <= response.status_code < 600 and attempt < 4:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"Fivetran API request failed after retries: {path}")

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page_params = {"limit": 1000, **(params or {})}
            if cursor:
                page_params["cursor"] = cursor
            payload = self.get(path, page_params)
            data = payload.get("data", {})
            items.extend(data.get("items", []))
            cursor = data.get("next_cursor")
            if not cursor:
                return items

    def groups(self) -> list[dict[str, Any]]:
        return self.paginate("/v1/groups")

    def connections_for_group(self, group_id: str) -> list[dict[str, Any]]:
        return self.paginate(f"/v1/groups/{group_id}/connections")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_configuration(settings: Settings) -> None:
    missing = []
    for name, value in {
        "FIVETRAN_API_KEY": settings.fivetran_api_key,
        "FIVETRAN_API_SECRET": settings.fivetran_api_secret,
        "SNOWFLAKE_ACCOUNT": settings.snowflake_account,
        "SNOWFLAKE_USER": settings.snowflake_user,
        "SNOWFLAKE_ROLE": settings.snowflake_role,
        "SNOWFLAKE_WAREHOUSE": settings.snowflake_warehouse,
    }.items():
        if not value:
            missing.append(name)
    if (
        not settings.snowflake_password
        and not settings.snowflake_private_key_path
        and settings.snowflake_authenticator.lower() != "externalbrowser"
    ):
        missing.append("SNOWFLAKE_PASSWORD, SNOWFLAKE_PRIVATE_KEY_PATH, or SNOWFLAKE_AUTHENTICATOR=externalbrowser")
    if missing:
        raise RuntimeError("Missing required configuration: " + ", ".join(missing))


def create_objects(connection, settings: Settings) -> None:
    db = settings.snowflake_database
    raw = settings.snowflake_raw_schema
    staging = settings.snowflake_staging_schema
    analytics = settings.snowflake_analytics_schema

    groups_table = qualified_name(db, raw, "GROUPS")
    connections_table = qualified_name(db, raw, "CONNECTIONS")

    statements = [
        f"create database if not exists {quote_ident(db)}",
        f"create schema if not exists {qualified_name(db, raw)}",
        f"create schema if not exists {qualified_name(db, staging)}",
        f"create schema if not exists {qualified_name(db, analytics)}",
        f"""
        create table if not exists {groups_table} (
            group_id varchar not null,
            group_name varchar not null,
            created_at timestamp_tz,
            loaded_at timestamp_tz not null,
            raw_payload variant not null,
            primary key (group_id)
        )
        """,
        f"""
        create table if not exists {connections_table} (
            connection_id varchar not null,
            group_id varchar not null,
            service varchar not null,
            schema_name varchar not null,
            paused boolean not null,
            setup_state varchar,
            sync_state varchar,
            update_state varchar,
            succeeded_at timestamp_tz,
            failed_at timestamp_tz,
            created_at timestamp_tz,
            sync_frequency_minutes integer,
            schedule_type varchar,
            loaded_at timestamp_tz not null,
            raw_payload variant not null,
            primary key (connection_id)
        )
        """,
    ]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        cursor.execute(f"use database {quote_ident(db)}")
        cursor.execute(f"use schema {qualified_name(db, raw)}")


def upsert_groups(connection, settings: Settings, groups: list[dict[str, Any]]) -> None:
    if not groups:
        return
    table = qualified_name(settings.snowflake_database, settings.snowflake_raw_schema, "GROUPS")
    loaded_at = datetime.now(timezone.utc)
    rows = [
        (
            group["id"],
            group["name"],
            parse_timestamp(group.get("created_at")),
            loaded_at,
            json.dumps(group, sort_keys=True),
        )
        for group in groups
    ]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            create temporary table TMP_FIVETRAN_GROUPS (
                group_id varchar,
                group_name varchar,
                created_at timestamp_tz,
                loaded_at timestamp_tz,
                raw_payload varchar
            )
            """
        )
        cursor.executemany(
            """
            insert into TMP_FIVETRAN_GROUPS
            (group_id, group_name, created_at, loaded_at, raw_payload)
            values (%s, %s, %s, %s, %s)
            """,
            rows,
        )
        cursor.execute(
            f"""
            merge into {table} as target
            using (
                select group_id, group_name, created_at, loaded_at, parse_json(raw_payload) as raw_payload
                from TMP_FIVETRAN_GROUPS
            ) as source
            on target.group_id = source.group_id
            when matched then update set
                group_name = source.group_name,
                created_at = source.created_at,
                loaded_at = source.loaded_at,
                raw_payload = source.raw_payload
            when not matched then insert
                (group_id, group_name, created_at, loaded_at, raw_payload)
            values
                (source.group_id, source.group_name, source.created_at, source.loaded_at, source.raw_payload)
            """
        )


def upsert_connections(connection, settings: Settings, connections: list[dict[str, Any]]) -> None:
    if not connections:
        return
    table = qualified_name(settings.snowflake_database, settings.snowflake_raw_schema, "CONNECTIONS")
    loaded_at = datetime.now(timezone.utc)
    rows = []
    for item in connections:
        status = item.get("status") or {}
        rows.append(
            (
                item["id"],
                item["group_id"],
                item["service"],
                item["schema"],
                bool(item.get("paused", False)),
                status.get("setup_state"),
                status.get("sync_state"),
                status.get("update_state"),
                parse_timestamp(status.get("succeeded_at")),
                parse_timestamp(status.get("failed_at")),
                parse_timestamp(item.get("created_at")),
                item.get("sync_frequency"),
                item.get("schedule_type"),
                loaded_at,
                json.dumps(item, sort_keys=True),
            )
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            create temporary table TMP_FIVETRAN_CONNECTIONS (
                connection_id varchar,
                group_id varchar,
                service varchar,
                schema_name varchar,
                paused boolean,
                setup_state varchar,
                sync_state varchar,
                update_state varchar,
                succeeded_at timestamp_tz,
                failed_at timestamp_tz,
                created_at timestamp_tz,
                sync_frequency_minutes integer,
                schedule_type varchar,
                loaded_at timestamp_tz,
                raw_payload varchar
            )
            """
        )
        cursor.executemany(
            """
            insert into TMP_FIVETRAN_CONNECTIONS
            (connection_id, group_id, service, schema_name, paused, setup_state, sync_state,
             update_state, succeeded_at, failed_at, created_at, sync_frequency_minutes,
             schedule_type, loaded_at, raw_payload)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        cursor.execute(
            f"""
            merge into {table} as target
            using (
                select
                    connection_id,
                    group_id,
                    service,
                    schema_name,
                    paused,
                    setup_state,
                    sync_state,
                    update_state,
                    succeeded_at,
                    failed_at,
                    created_at,
                    sync_frequency_minutes,
                    schedule_type,
                    loaded_at,
                    parse_json(raw_payload) as raw_payload
                from TMP_FIVETRAN_CONNECTIONS
            ) as source
            on target.connection_id = source.connection_id
            when matched then update set
                group_id = source.group_id,
                service = source.service,
                schema_name = source.schema_name,
                paused = source.paused,
                setup_state = source.setup_state,
                sync_state = source.sync_state,
                update_state = source.update_state,
                succeeded_at = source.succeeded_at,
                failed_at = source.failed_at,
                created_at = source.created_at,
                sync_frequency_minutes = source.sync_frequency_minutes,
                schedule_type = source.schedule_type,
                loaded_at = source.loaded_at,
                raw_payload = source.raw_payload
            when not matched then insert
                (connection_id, group_id, service, schema_name, paused, setup_state, sync_state,
                 update_state, succeeded_at, failed_at, created_at, sync_frequency_minutes,
                 schedule_type, loaded_at, raw_payload)
            values
                (source.connection_id, source.group_id, source.service, source.schema_name,
                 source.paused, source.setup_state, source.sync_state, source.update_state,
                 source.succeeded_at, source.failed_at, source.created_at, source.sync_frequency_minutes,
                 source.schedule_type, source.loaded_at, source.raw_payload)
            """
        )


def collect_fivetran_metadata(settings: Settings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client = FivetranClient(settings)
    groups = client.groups()
    connections: list[dict[str, Any]] = []
    for group in groups:
        connections.extend(client.connections_for_group(group["id"]))
    return groups, connections


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Load live Fivetran metadata into Snowflake.")
    parser.add_argument("--bootstrap-only", action="store_true", help="Create Snowflake objects and exit.")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    require_configuration(settings)

    with connect(settings) as snowflake_connection:
        create_objects(snowflake_connection, settings)
        if args.bootstrap_only:
            print("Snowflake objects are ready.")
            return 0

        groups, connections = collect_fivetran_metadata(settings)
        upsert_groups(snowflake_connection, settings, groups)
        upsert_connections(snowflake_connection, settings, connections)
        print(f"Loaded {len(groups)} Fivetran groups and {len(connections)} connections.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
