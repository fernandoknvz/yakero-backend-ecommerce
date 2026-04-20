from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Yakero Ecommerce API"
    debug: bool = False
    testing: bool = False
    api_base_url: str = "https://api.yakero.cl"

    # Database (asyncmy driver for async SQLAlchemy)
    database_url: str = "mysql+asyncmy://user:pass@localhost:3306/yakero_ecommerce"

    # JWT
    jwt_secret: str = "CHANGE_THIS_IN_PRODUCTION"
    jwt_expire_minutes: int = 1440  # 24 horas

    # MercadoPago
    mp_access_token: str = ""
    mp_webhook_secret: str = ""
    mp_back_url_success: str = "https://yakero.cl/checkout/success"
    mp_back_url_failure: str = "https://yakero.cl/checkout/failure"
    mp_back_url_pending: str = "https://yakero.cl/checkout/pending"

    # Store location (para cálculo de delivery)
    store_lat: float = -33.4094
    store_lon: float = -70.5799

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "https://yakero.cl"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
