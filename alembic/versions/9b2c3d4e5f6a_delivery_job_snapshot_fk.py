"""allow immutable delivery jobs to survive endpoint deletion

Revision ID: 9b2c3d4e5f6a
Revises: 8a1b2c3d4e5f
"""
from alembic import op

revision = "9b2c3d4e5f6a"
down_revision = "8a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("email_delivery_jobs_endpoint_id_fkey", "email_delivery_jobs", type_="foreignkey")
    op.alter_column("email_delivery_jobs", "endpoint_id", nullable=True)
    op.create_foreign_key(
        "email_delivery_jobs_endpoint_id_fkey",
        "email_delivery_jobs",
        "form_endpoints",
        ["endpoint_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("email_delivery_jobs_endpoint_id_fkey", "email_delivery_jobs", type_="foreignkey")
    op.alter_column("email_delivery_jobs", "endpoint_id", nullable=False)
    op.create_foreign_key(
        "email_delivery_jobs_endpoint_id_fkey",
        "email_delivery_jobs",
        "form_endpoints",
        ["endpoint_id"],
        ["id"],
    )
