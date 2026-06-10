from __future__ import annotations

from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

from data_ops.settings import Settings


def quote_ident(identifier: str) -> str:
    if not identifier:
        raise ValueError("Snowflake identifier cannot be empty")
    return '"' + identifier.replace('"', '""') + '"'


def qualified_name(*parts: str) -> str:
    return ".".join(quote_ident(part) for part in parts)


def _private_key_der(settings: Settings) -> bytes:
    key_path = Path(settings.snowflake_private_key_path).expanduser()
    passphrase = settings.snowflake_private_key_passphrase.encode() or None
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=passphrase)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect(settings: Settings, *, database: str | None = None, schema: str | None = None):
    params: dict[str, object] = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "role": settings.snowflake_role,
        "warehouse": settings.snowflake_warehouse,
        "client_session_keep_alive": False,
    }

    if database:
        params["database"] = database
    if schema:
        params["schema"] = schema

    if settings.snowflake_private_key_path:
        params["private_key"] = _private_key_der(settings)
    else:
        params["password"] = settings.snowflake_password

    return snowflake.connector.connect(**params)

