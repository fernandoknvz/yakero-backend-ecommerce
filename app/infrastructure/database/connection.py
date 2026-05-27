import ssl
from typing import Any

from sqlalchemy.engine import URL, make_url


def build_async_engine_config(database_url: str, **engine_options: Any) -> tuple[URL, dict[str, Any]]:
    url = make_url(database_url)
    options = dict(engine_options)

    if url.drivername == "mysql+aiomysql" and _is_truthy(url.query.get("ssl")):
        url = url.difference_update_query(["ssl"])
        connect_args = dict(options.get("connect_args") or {})
        connect_args.setdefault("ssl", ssl.create_default_context())
        options["connect_args"] = connect_args

    return url, options


def _is_truthy(value: Any) -> bool:
    if isinstance(value, tuple):
        value = value[-1] if value else None
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "required"}
    return bool(value)
