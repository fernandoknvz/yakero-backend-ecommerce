from app.config import DEFAULT_ALLOWED_ORIGINS, Settings


def test_allowed_origins_include_current_frontend_and_localhost_defaults():
    settings = Settings(
        jwt_secret="test-secret",
        allowed_origins="https://legacy.example.com/",
        frontend_public_url="https://ecommerce.fernandoolgueadev.cl/",
    )

    assert settings.allowed_origins[:3] == DEFAULT_ALLOWED_ORIGINS
    assert "https://ecommerce.fernandoolgueadev.cl" in settings.allowed_origins
    assert "http://localhost:5173" in settings.allowed_origins
    assert "http://localhost:3000" in settings.allowed_origins
    assert "https://legacy.example.com" in settings.allowed_origins
    assert "https://legacy.example.com/" not in settings.allowed_origins


def test_allowed_origins_parse_json_array():
    settings = Settings(
        jwt_secret="test-secret",
        allowed_origins='["https://front.test/", "http://localhost:5173"]',
    )

    assert "https://front.test" in settings.allowed_origins
    assert settings.allowed_origins.count("http://localhost:5173") == 1
