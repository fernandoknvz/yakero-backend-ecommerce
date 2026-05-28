import ssl
from typing import Any

from sqlalchemy.engine import URL, make_url


SSL_QUERY_KEYS = ("ssl", "ssl-mode", "ssl_mode")
SSL_REQUIRED_VALUES = {"1", "true", "yes", "y", "on", "required", "preferred", "verify_ca", "verify_identity"}


def build_async_engine_config(database_url: str, **engine_options: Any) -> tuple[URL, dict[str, Any]]:
    url = make_url(database_url)
    options = dict(engine_options)

    if url.drivername == "mysql+aiomysql" and _requires_ssl(url):
        url = url.difference_update_query(SSL_QUERY_KEYS)
        connect_args = dict(options.get("connect_args") or {})
        connect_args.setdefault("ssl", ssl.create_default_context())
        options["connect_args"] = connect_args

    return url, options


def _requires_ssl(url: URL) -> bool:
    return any(_is_truthy(url.query.get(key)) for key in SSL_QUERY_KEYS)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, tuple):
        value = value[-1] if value else None
    if isinstance(value, str):
        return value.strip().lower() in SSL_REQUIRED_VALUES
    return bool(value)
