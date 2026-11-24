"""Precompute simplified city boundaries for the map endpoint.

Revision ID: d8a74e1b9c02
Revises: c15fbc26e001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op

revision: str = "d8a74e1b9c02"
down_revision: str | Sequence[str] | None = "c15fbc26e001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "city",
        sa.Column(
            "geom_boundary_simplified",
            Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )
    op.execute(
        """
        CREATE FUNCTION set_city_boundary_simplified()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.geom_boundary_simplified =
                CASE
                    WHEN NEW.geom_boundary IS NULL THEN NULL
                    ELSE ST_SimplifyPreserveTopology(NEW.geom_boundary, 0.002)
                END;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_city_boundary_simplified
        BEFORE INSERT OR UPDATE OF geom_boundary ON city
        FOR EACH ROW EXECUTE FUNCTION set_city_boundary_simplified()
        """
    )
    op.execute(
        """
        UPDATE city
        SET geom_boundary_simplified =
            ST_SimplifyPreserveTopology(geom_boundary, 0.002)
        WHERE geom_boundary IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_city_boundary_simplified ON city")
    op.execute("DROP FUNCTION set_city_boundary_simplified()")
    op.drop_column("city", "geom_boundary_simplified")
