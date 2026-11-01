"""Persist node population weights for portable simulations.

Revision ID: c15fbc26e001
Revises: 9b7a1c2d3e4f
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c15fbc26e001"
down_revision: str | Sequence[str] | None = "9b7a1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL identifies previous runs that do not have per-node population data.
    op.add_column("node", sa.Column("population_weight", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("node", "population_weight")
