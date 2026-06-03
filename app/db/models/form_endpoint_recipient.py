from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FormEndpointRecipient(TimestampMixin, Base):
    __tablename__ = "form_endpoint_recipients"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    endpoint_id: Mapped[int] = mapped_column(ForeignKey("form_endpoints.id"), nullable=False, index=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    recipient_type: Mapped[str] = mapped_column(String(20), nullable=False, default="to")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)