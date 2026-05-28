from ssl import SSLContext

from app.infrastructure.database.connection import build_async_engine_config


def test_mysql_aiomysql_ssl_true_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl=true",
        pool_pre_ping=True,
    )

    assert "ssl" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)
    assert options["pool_pre_ping"] is True


def test_mysql_aiomysql_aiven_ssl_mode_adds_ssl_context_and_strips_query_flag():
    url, options = build_async_engine_config(
        "mysql+aiomysql://user:pass@mysql.test:3306/yakero?ssl-mode=REQUIRED"
    )

    assert "ssl-mode" not in url.query
    assert isinstance(options["connect_args"]["ssl"], SSLContext)
