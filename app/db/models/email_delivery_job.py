from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmailDeliveryJob(TimestampMixin, Base):
    """A queued delivery whose encrypted_payload is a complete immutable delivery snapshot.

    endpoint_id is nullable reporting/history metadata only. Workers must never dereference
    it for delivery configuration because the endpoint may change or be removed after acceptance.
    """
    __tablename__ = "email_delivery_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("form_endpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Versioned encrypted DeliverySnapshot JSON; destroyed on success or terminal failure.
    encrypted_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
