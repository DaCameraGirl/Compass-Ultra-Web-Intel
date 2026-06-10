create database if not exists identifier($database_name);

create schema if not exists identifier($database_name || '.' || $raw_schema_name);
create schema if not exists identifier($database_name || '.' || $staging_schema_name);
create schema if not exists identifier($database_name || '.' || $analytics_schema_name);

create table if not exists identifier($database_name || '.' || $raw_schema_name || '.GROUPS') (
    group_id varchar not null,
    group_name varchar not null,
    created_at timestamp_tz,
    loaded_at timestamp_tz not null,
    raw_payload variant not null,
    primary key (group_id)
);

create table if not exists identifier($database_name || '.' || $raw_schema_name || '.CONNECTIONS') (
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
);

