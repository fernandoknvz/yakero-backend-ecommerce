import ssl
from typing import Any

from sqlalchemy.engine import URL, make_url


SSL_QUERY_KEYS = ("ssl", "ssl-mode", "ssl_mode")
SSL_REQUIRED_VALUES = {"1", "true", "yes", "y", "on", "required", "preferred", "verify_ca", "verify_identity"}


def build_async_engine_config(
    database_url: str,
    *,
    ca_cert: str = "",
    ssl_insecure: bool = False,
    is_production: bool = False,
    **engine_options: Any,
) -> tuple[URL, dict[str, Any]]:
    url = make_url(database_url)
    options = dict(engine_options)

    if url.drivername == "mysql+aiomysql":
        options["pool_pre_ping"] = False
        if _requires_ssl(url):
            url = url.difference_update_query(SSL_QUERY_KEYS)
            connect_args = dict(options.get("connect_args") or {})
            connect_args.setdefault(
                "ssl",
                build_ssl_context(
                    ca_cert=ca_cert,
                    ssl_insecure=ssl_insecure,
                    is_production=is_production,
                ),
            )
            options["connect_args"] = connect_args

    return url, options


def build_ssl_context(
    *,
    ca_cert: str = "",
    ssl_insecure: bool = False,
    is_production: bool = False,
) -> ssl.SSLContext:
    if ssl_insecure and is_production:
        raise ValueError("AIVEN_SSL_INSECURE no esta permitido en produccion.")

    normalized_ca_cert = _normalize_ca_cert(ca_cert)
    context = ssl.create_default_context(cadata=normalized_ca_cert or None)

    if ssl_insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context


def database_connection_diagnostics(
    database_url: str,
    ssl_enabled: bool,
    ca_cert_configured: bool = False,
    ssl_insecure: bool = False,
) -> dict[str, Any]:
    url = make_url(database_url)
    return {
        "driver": url.drivername,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "user": url.username,
        "query": dict(url.query),
        "ssl_enabled": ssl_enabled,
        "ssl_ca_configured": ca_cert_configured,
        "ssl_insecure": ssl_insecure,
    }


def has_ssl_context(engine_options: dict[str, Any]) -> bool:
    connect_args = engine_options.get("connect_args") or {}
    return "ssl" in connect_args


def _requires_ssl(url: URL) -> bool:
    return any(_is_truthy(url.query.get(key)) for key in SSL_QUERY_KEYS)


def _normalize_ca_cert(ca_cert: str) -> str:
    return ca_cert.strip().replace("\\n", "\n")


def _is_truthy(value: Any) -> bool:
    if isinstance(value, tuple):
        value = value[-1] if value else None
    if isinstance(value, str):
        return value.strip().lower() in SSL_REQUIRED_VALUES
    return bool(value)
