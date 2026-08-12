"""add encrypted email delivery queue

Revision ID: 8a1b2c3d4e5f
Revises: 7f0a1c2d3e4f
"""
from alembic import op
import sqlalchemy as sa

revision = "8a1b2c3d4e5f"
down_revision = "7f0a1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_delivery_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint_id", sa.Integer(), sa.ForeignKey("form_endpoints.id"), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("endpoint_id", "status", "available_at", "terminal_at"):
        op.create_index(f"ix_email_delivery_jobs_{column}", "email_delivery_jobs", [column])
    op.add_column("endpoint_delivery_logs", sa.Column("delivery_job_id", sa.Integer(), nullable=True))
    op.add_column("endpoint_delivery_logs", sa.Column("delivery_status", sa.String(30), nullable=True))
    op.create_index("ix_endpoint_delivery_logs_delivery_job_id", "endpoint_delivery_logs", ["delivery_job_id"])


def downgrade() -> None:
    op.drop_index("ix_endpoint_delivery_logs_delivery_job_id", table_name="endpoint_delivery_logs")
    op.drop_column("endpoint_delivery_logs", "delivery_status")
    op.drop_column("endpoint_delivery_logs", "delivery_job_id")
    op.drop_table("email_delivery_jobs")
