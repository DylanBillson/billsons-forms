from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Billson's Forms"
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str
    app_encryption_key: str

    base_url: str = "http://localhost:8000"
    default_timezone: str = "Europe/London"

    database_url: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()