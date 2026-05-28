from ssl import SSLContext

from app.infrastructure.database.connection import (
    build_async_engine_config,
    database_connection_diagnostics,
    has_ssl_context,
)


def test_mysql_aiomysql_ssl_true_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl=true",
        pool_pre_ping=True,
    )

    assert "ssl" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)
    assert has_ssl_context(options)
    assert options["pool_pre_ping"] is True


def test_mysql_aiomysql_aiven_ssl_mode_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl-mode=REQUIRED"
    )

    assert "ssl-mode" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)


def test_database_connection_diagnostics_do_not_include_password():
    diagnostics = database_connection_diagnostics(
        "mysql+aiomysql://avnadmin:secret@mysql.test:27671/defaultdb?ssl=1",
        ssl_enabled=True,
    )

    assert diagnostics == {
        "driver": "mysql+aiomysql",
        "host": "mysql.test",
        "port": 27671,
        "database": "defaultdb",
        "user": "avnadmin",
        "query": {"ssl": "1"},
        "ssl_enabled": True,
    }
    assert "secret" not in str(diagnostics)
