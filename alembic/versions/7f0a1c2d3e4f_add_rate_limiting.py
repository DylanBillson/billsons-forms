"""add rate limiting

Revision ID: 7f0a1c2d3e4f
Revises: e5a669540334
"""
from alembic import op
import sqlalchemy as sa

revision = "7f0a1c2d3e4f"
down_revision = "e5a669540334"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("form_endpoints", sa.Column("rate_limit_enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("form_endpoints", sa.Column("rate_limit_requests", sa.Integer(), server_default="30", nullable=False))
    op.add_column("form_endpoints", sa.Column("rate_limit_window_seconds", sa.Integer(), server_default="60", nullable=False))
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(150), nullable=False),
        sa.Column("subject_key", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scope", "subject_key", "window_start", name="uq_rate_limit_bucket"),
    )
    op.create_index("ix_rate_limit_buckets_scope", "rate_limit_buckets", ["scope"])
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_column("form_endpoints", "rate_limit_window_seconds")
    op.drop_column("form_endpoints", "rate_limit_requests")
    op.drop_column("form_endpoints", "rate_limit_enabled")
