from functools import lru_cache
import json
from urllib.parse import urlparse
from typing import Any

from pydantic import model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "Yakero Ecommerce API"
    environment: str = "development"
    debug: bool = False
    testing: bool = False
    api_base_url: str = "https://api.yakero.cl"
    api_v1_prefix: str = "/api/v1"

    # Database (asyncmy driver for async SQLAlchemy)
    database_url: str = "mysql+asyncmy://user:pass@localhost:3306/yakero_ecommerce"

    # JWT
    jwt_secret: str = "CHANGE_THIS_IN_PRODUCTION"
    jwt_expire_minutes: int = 1440  # 24 horas

    # MercadoPago
    mp_access_token: str = ""
    mp_public_key: str = ""
    mp_env: str = "sandbox"
    mp_webhook_secret: str = ""
    mp_back_url_success: str = "https://yakero.cl/checkout/success"
    mp_back_url_failure: str = "https://yakero.cl/checkout/failure"
    mp_back_url_pending: str = "https://yakero.cl/checkout/pending"
    app_base_url: str = "http://localhost:5173"

    # Store location (para cálculo de delivery)
    store_lat: float = -33.4094
    store_lon: float = -70.5799

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "https://yakero.cl"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            if value.strip().startswith("["):
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return cls.model_fields["allowed_origins"].default

    @field_validator("debug", "testing", mode="before")
    @classmethod
    def parse_bool_flags(cls, value: Any) -> bool:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on", "debug", "dev"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", "release", "prod", "production"}:
                return False
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def has_insecure_jwt_secret(self) -> bool:
        return self.jwt_secret in {
            "",
            "CHANGE_THIS_IN_PRODUCTION",
            "CAMBIA_ESTO_EN_PRODUCCION_CON_OPENSSL_RAND_HEX_32",
        }

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        if not self.api_v1_prefix.startswith("/"):
            raise ValueError("API_V1_PREFIX debe comenzar con '/'.")
        if self.api_v1_prefix != "/" and self.api_v1_prefix.endswith("/"):
            raise ValueError("API_V1_PREFIX no debe terminar con '/'.")
        if self.jwt_expire_minutes <= 0:
            raise ValueError("JWT_EXPIRE_MINUTES debe ser mayor que 0.")
        if not self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS no puede estar vacio.")
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG debe estar deshabilitado en produccion.")
            if self.has_insecure_jwt_secret:
                raise ValueError("JWT_SECRET inseguro para produccion.")
            if "*" in self.allowed_origins:
                raise ValueError("CORS wildcard no esta permitido en produccion.")
        return self

    def public_runtime_diagnostics(self) -> dict[str, Any]:
        database = urlparse(self.database_url)
        return {
            "environment": self.environment,
            "debug": self.debug,
            "api_v1_prefix": self.api_v1_prefix,
            "database_host": database.hostname,
            "database_name": database.path.lstrip("/"),
            "allowed_origins": self.allowed_origins,
            "jwt_insecure": self.has_insecure_jwt_secret,
        }


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
