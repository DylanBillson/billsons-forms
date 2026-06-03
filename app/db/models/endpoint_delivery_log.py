from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EndpointDeliveryLog(TimestampMixin, Base):
    __tablename__ = "endpoint_delivery_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("form_endpoints.id"),
        nullable=False,
        index=True,
    )

    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    cap_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    recipient_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)