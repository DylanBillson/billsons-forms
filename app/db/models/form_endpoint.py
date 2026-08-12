from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FormEndpoint(TimestampMixin, Base):
    __tablename__ = "form_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Form behaviour
    success_redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_origins: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reply-To behaviour
    reply_to_field: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Email content
    email_subject: Mapped[str] = mapped_column(String(255), nullable=False, default="New form submission")
    email_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SMTP settings, per endpoint
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_security: Mapped[str] = mapped_column(String(50), nullable=False, default="starttls")

    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cap.js settings, per endpoint
    cap_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cap_verify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cap_site_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cap_secret_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Basic limits
    max_payload_kb: Mapped[int] = mapped_column(Integer, nullable=False, default=256)
    rate_limit_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
