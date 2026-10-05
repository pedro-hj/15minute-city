"""Add population-weighted accessibility metrics.

Revision ID: 9b7a1c2d3e4f
Revises: 6e0e51752629
"""

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op

revision: str = "9b7a1c2d3e4f"
down_revision: str | Sequence[str] | None = "6e0e51752629"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "city",
        "geom_boundary",
        existing_type=Geometry("POLYGON", srid=4326),
        type_=Geometry("GEOMETRY", srid=4326),
        postgresql_using="geom_boundary::geometry",
    )
    op.create_unique_constraint("uq_city_name_country", "city", ["name", "country"])
    op.create_unique_constraint(
        "uq_category_osm_tag",
        "category_osm_tag",
        ["category_id", "osm_key", "osm_value"],
    )
    op.create_unique_constraint(
        "uq_node_execution_osm", "node", ["execution_id", "osm_id"]
    )
    op.add_column(
        "execution",
        sa.Column(
            "threshold_minutes",
            sa.Float(),
            nullable=False,
            server_default="15.0",
        ),
    )
    op.add_column(
        "execution",
        sa.Column(
            "network_type",
            sa.String(length=50),
            nullable=False,
            server_default="walk",
        ),
    )
    op.add_column("execution", sa.Column("pbf_source", sa.String(1024)))
    op.add_column("execution", sa.Column("pbf_checksum", sa.String(64)))
    op.add_column("execution", sa.Column("population_source", sa.String(1024)))
    op.add_column("execution", sa.Column("population_column", sa.String(255)))
    op.add_column("execution", sa.Column("error_message", sa.String(2048)))
    op.add_column("execution", sa.Column("analysis_metadata", sa.JSON()))

    op.add_column(
        "node_reachability",
        sa.Column("reachable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("node_reachability", "travel_time_minutes", nullable=True)

    op.add_column(
        "city_index",
        sa.Column(
            "origin_strategy",
            sa.String(length=50),
            nullable=False,
            server_default="network_nodes",
        ),
    )
    op.add_column(
        "city_index",
        sa.Column(
            "weight_unit",
            sa.String(length=50),
            nullable=False,
            server_default="node_count",
        ),
    )
    op.add_column(
        "city_index",
        sa.Column(
            "threshold_minutes", sa.Float(), nullable=False, server_default="15.0"
        ),
    )
    for column_name in (
        "total_weight",
        "reachable_weight",
        "within_threshold_weight",
        "unreachable_weight",
        "unreachable_percentage",
    ):
        op.add_column(
            "city_index",
            sa.Column(column_name, sa.Float(), nullable=False, server_default="0.0"),
        )
    op.add_column("city_index", sa.Column("median_travel_time_minutes", sa.Float()))
    op.alter_column("city_index", "mean_travel_time_minutes", nullable=True)
    op.execute(
        "UPDATE city_index "
        "SET origin_strategy = 'legacy_network_nodes', "
        "weight_unit = 'legacy_node_count'"
    )
    op.drop_constraint("city_index_pkey", "city_index", type_="primary")
    op.create_primary_key(
        "city_index_pkey",
        "city_index",
        ["execution_id", "category_id", "origin_strategy"],
    )

    op.create_table(
        "accessibility_summary",
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("origin_strategy", sa.String(50), nullable=False),
        sa.Column("weight_unit", sa.String(50), nullable=False),
        sa.Column("threshold_minutes", sa.Float(), nullable=False),
        sa.Column("total_weight", sa.Float(), nullable=False),
        sa.Column("overall_coverage_percentage", sa.Float(), nullable=False),
        sa.Column("overall_unreachable_percentage", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["execution.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("execution_id", "origin_strategy"),
    )


def downgrade() -> None:
    op.drop_constraint("uq_node_execution_osm", "node", type_="unique")
    op.drop_constraint("uq_category_osm_tag", "category_osm_tag", type_="unique")
    op.drop_constraint("uq_city_name_country", "city", type_="unique")
    op.alter_column(
        "city",
        "geom_boundary",
        existing_type=Geometry("GEOMETRY", srid=4326),
        type_=Geometry("POLYGON", srid=4326),
        postgresql_using="ST_GeometryN(geom_boundary, 1)",
    )
    op.drop_table("accessibility_summary")
    op.drop_constraint("city_index_pkey", "city_index", type_="primary")
    op.create_primary_key(
        "city_index_pkey", "city_index", ["execution_id", "category_id"]
    )
    op.alter_column("city_index", "mean_travel_time_minutes", nullable=False)
    op.drop_column("city_index", "median_travel_time_minutes")
    for column_name in (
        "unreachable_percentage",
        "unreachable_weight",
        "within_threshold_weight",
        "reachable_weight",
        "total_weight",
        "threshold_minutes",
        "weight_unit",
        "origin_strategy",
    ):
        op.drop_column("city_index", column_name)

    for column_name in (
        "error_message",
        "analysis_metadata",
        "population_column",
        "population_source",
        "pbf_checksum",
        "pbf_source",
        "network_type",
        "threshold_minutes",
    ):
        op.drop_column("execution", column_name)

    op.execute(
        "UPDATE node_reachability SET travel_time_minutes = 0 "
        "WHERE travel_time_minutes IS NULL"
    )
    op.alter_column("node_reachability", "travel_time_minutes", nullable=False)
    op.drop_column("node_reachability", "reachable")
