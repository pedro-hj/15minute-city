"""Create public analysis queue and stable IBGE city identity.

Revision ID: a1b2c3d4e5f6
Revises: 9b7a1c2d3e4f
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "9b7a1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("city", sa.Column("ibge_code", sa.String(7), nullable=True))
    op.add_column("city", sa.Column("state", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_city_ibge_code", "city", ["ibge_code"])
    op.drop_constraint("uq_city_name_country", "city", type_="unique")
    op.create_table(
        "analysis_request",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ibge_code", sa.String(7), nullable=False),
        sa.Column("city_name", sa.String(255), nullable=False),
        sa.Column("state_name", sa.String(100), nullable=False),
        sa.Column("requester_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_city_id", sa.Integer(), sa.ForeignKey("city.id", ondelete="SET NULL")),
        sa.Column("error_message", sa.String(512), nullable=True),
    )
    op.create_index(
        "uq_analysis_request_active_city",
        "analysis_request",
        ["ibge_code"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )
    op.create_index(
        "ix_analysis_request_requester_time",
        "analysis_request",
        ["requester_hash", "requested_at"],
    )
    op.create_index(
        "ix_analysis_request_status_time",
        "analysis_request",
        ["status", "requested_at"],
    )
    op.create_index("ix_analysis_request_ibge_code", "analysis_request", ["ibge_code"])


def downgrade() -> None:
    op.drop_table("analysis_request")
    op.create_unique_constraint("uq_city_name_country", "city", ["name", "country"])
    op.drop_constraint("uq_city_ibge_code", "city", type_="unique")
    op.drop_column("city", "state")
    op.drop_column("city", "ibge_code")
