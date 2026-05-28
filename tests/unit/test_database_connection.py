import ssl
from ssl import SSLContext

import pytest

from app.infrastructure.database.connection import (
    build_ssl_context,
    build_async_engine_config,
    database_connection_diagnostics,
    has_ssl_context,
)


CA_CERT = """-----BEGIN CERTIFICATE-----
test-certificate-body
-----END CERTIFICATE-----"""


def test_mysql_aiomysql_ssl_true_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl=true",
        pool_pre_ping=True,
    )

    assert "ssl" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)
    assert has_ssl_context(options)
    assert options["pool_pre_ping"] is True


def test_mysql_aiomysql_ssl_uses_aiven_ca_cert(monkeypatch):
    captured = {}

    def fake_create_default_context(*, cadata=None):
        captured["cadata"] = cadata
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)

    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl=1",
        ca_cert=CA_CERT.replace("\n", "\\n"),
    )

    ssl_context = options["connect_args"]["ssl"]
    assert "ssl" not in url.query
    assert isinstance(ssl_context, SSLContext)
    assert captured["cadata"] == CA_CERT


def test_mysql_aiomysql_aiven_ssl_mode_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl-mode=REQUIRED"
    )

    assert "ssl-mode" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)


def test_ssl_insecure_is_debug_only_and_disables_verification_outside_production():
    ssl_context = build_ssl_context(ssl_insecure=True, is_production=False)

    assert ssl_context.verify_mode == ssl.CERT_NONE
    assert ssl_context.check_hostname is False


def test_ssl_insecure_is_blocked_in_production():
    with pytest.raises(ValueError, match="AIVEN_SSL_INSECURE"):
        build_ssl_context(ssl_insecure=True, is_production=True)


def test_database_connection_diagnostics_do_not_include_password():
    diagnostics = database_connection_diagnostics(
        "mysql+aiomysql://avnadmin:secret@mysql.test:27671/defaultdb?ssl=1",
        ssl_enabled=True,
        ca_cert_configured=True,
    )

    assert diagnostics == {
        "driver": "mysql+aiomysql",
        "host": "mysql.test",
        "port": 27671,
        "database": "defaultdb",
        "user": "avnadmin",
        "query": {"ssl": "1"},
        "ssl_enabled": True,
        "ssl_ca_configured": True,
        "ssl_insecure": False,
    }
    assert "secret" not in str(diagnostics)
    assert "CERTIFICATE" not in str(diagnostics)
