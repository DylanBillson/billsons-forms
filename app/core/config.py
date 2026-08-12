from __future__ import annotations

import ipaddress
import os
from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Billson's Forms"
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = "development-only-change-me"
    app_encryption_key: str = "lvrmNO5YoDl8_pLcV4H_nTpg4LS7WwO8qSkEubdg76E="
    base_url: str = "http://localhost:8000"
    default_timezone: str = "Europe/London"
    database_url: str = "postgresql+psycopg://billsons_forms:billsons_forms@db:5432/billsons_forms"

    trusted_proxies: str = "127.0.0.1/32,::1/128"
    session_lifetime_hours: int = 336
    secure_cookies: bool = True
    login_rate_limit_requests: int = 10
    login_rate_limit_window_seconds: int = 900
    default_form_rate_limit_requests: int = 30
    default_form_rate_limit_window_seconds: int = 60
    absolute_max_payload_kb: int = 1024
    smtp_timeout_seconds: float = 20.0

    delivery_log_retention_days: int = 365
    audit_log_retention_days: int = 730
    expired_session_retention_days: int = 30
    rate_limit_retention_hours: int = 0
    queue_terminal_retention_days: int = 7
    cleanup_interval_seconds: int = 3600
    queue_max_attempts: int = 6
    queue_poll_seconds: float = 2.0
    queue_lock_timeout_seconds: int = 300
    queue_heartbeat_seconds: int = 60

    model_config = SettingsConfigDict(
        # Compose injects DATABASE_URL (and the remaining settings) into the
        # process. In that case do not parse a bind-mounted development .env a
        # second time. Direct local Python runs still load .env as before.
        env_file=None if os.environ.get("DATABASE_URL") else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("session_lifetime_hours", "absolute_max_payload_kb", "queue_lock_timeout_seconds", "queue_heartbeat_seconds")
    @classmethod
    def positive_values(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_queue_timing(self):
        if self.queue_heartbeat_seconds >= self.queue_lock_timeout_seconds:
            raise ValueError("QUEUE_HEARTBEAT_SECONDS must be shorter than QUEUE_LOCK_TIMEOUT_SECONDS")
        return self

    @property
    def trusted_proxy_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        return tuple(
            ipaddress.ip_network(item.strip(), strict=False)
            for item in self.trusted_proxies.split(",")
            if item.strip()
        )

    def production_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            errors.append("DATABASE_URL must use PostgreSQL")
        if any(marker in self.database_url.lower() for marker in ("change-this", "replace-with", ":password@")):
            errors.append("DATABASE_URL must not contain a placeholder database password")
        if len(self.app_secret_key) < 32 or "change" in self.app_secret_key.lower():
            errors.append("APP_SECRET_KEY must be a non-placeholder secret of at least 32 characters")
        try:
            Fernet(self.app_encryption_key.encode("ascii"))
        except Exception:
            errors.append("APP_ENCRYPTION_KEY must be a valid Fernet key")
        if self.app_encryption_key == "lvrmNO5YoDl8_pLcV4H_nTpg4LS7WwO8qSkEubdg76E=":
            errors.append("APP_ENCRYPTION_KEY must not use the development placeholder key")
        if self.app_debug:
            errors.append("APP_DEBUG must be false in production")
        if not self.secure_cookies:
            errors.append("SECURE_COOKIES must be true in production")
        if not self.base_url.startswith("https://"):
            errors.append("BASE_URL must use HTTPS in production")
        try:
            if not self.trusted_proxy_networks:
                errors.append("TRUSTED_PROXIES must name the Traefik proxy network")
            broad_private = {
                ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("fc00::/7"),
            }
            if any(
                network.prefixlen == 0
                or network in broad_private
                or (network.is_private and network.version == 4 and network.prefixlen < 16)
                or (network.is_private and network.version == 6 and network.prefixlen < 64)
                for network in self.trusted_proxy_networks
            ):
                errors.append("TRUSTED_PROXIES must use the actual edge-network subnet, not a broad private or catch-all range")
        except ValueError:
            errors.append("TRUSTED_PROXIES contains an invalid IP network")
        return errors


settings = Settings()
