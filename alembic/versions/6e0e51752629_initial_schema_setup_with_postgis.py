"""Initial schema setup with PostGIS

Revision ID: 6e0e51752629
Revises: 
Create Date: 2026-07-21 21:51:38.439302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = '6e0e51752629'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('city',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the city'),
        sa.Column('name', sa.String(length=255), nullable=False, comment="City name (e.g., 'Paris', 'Praia Grande')"),
        sa.Column('country', sa.String(length=255), nullable=False, comment='Country name to which the city belongs'),
        sa.Column('geom_boundary', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True, comment='Geographic boundary polygon of the city extracted from OpenStreetMap (EPSG:4326)'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_city_country'), 'city', ['country'], unique=False)
    op.create_index(op.f('ix_city_name'), 'city', ['name'], unique=False)

    op.create_table('service_category',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the category'),
        sa.Column('code', sa.String(length=100), nullable=False, comment="Stable code identifier (e.g., 'saude', 'educacao')"),
        sa.Column('display_name', sa.String(length=255), nullable=False, comment="Human-readable category label (e.g., 'Health')"),
        sa.Column('moreno_pillar', sa.String(length=100), nullable=False, comment="Associated Moreno 15-Minute City pillar (e.g., 'health', 'education')"),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_category_code'), 'service_category', ['code'], unique=True)

    op.create_table('category_osm_tag',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the tag mapping'),
        sa.Column('category_id', sa.Integer(), nullable=False, comment='Foreign key referencing the service category'),
        sa.Column('osm_key', sa.String(length=100), nullable=False, comment="OpenStreetMap tag key (e.g., 'amenity', 'shop')"),
        sa.Column('osm_value', sa.String(length=100), nullable=False, comment="OpenStreetMap tag value (e.g., 'hospital', 'supermarket')"),
        sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_category_osm_tag_category_id'), 'category_osm_tag', ['category_id'], unique=False)

    op.create_table('execution',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the execution'),
        sa.Column('city_id', sa.Integer(), nullable=False, comment='Foreign key referencing the analyzed city'),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when the execution was initiated'),
        sa.Column('speed_kmh', sa.Float(), nullable=False, comment='Walking/transport speed parameter in km/h'),
        sa.Column('status', sa.String(length=50), nullable=False, comment="Execution status (e.g., 'processing', 'completed', 'error')"),
        sa.Column('execution_time_seconds', sa.Float(), nullable=True, comment='Total execution processing duration in seconds'),
        sa.ForeignKeyConstraint(['city_id'], ['city.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_execution_city_id'), 'execution', ['city_id'], unique=False)
    op.create_index(op.f('ix_execution_status'), 'execution', ['status'], unique=False)

    op.create_table('city_index',
        sa.Column('execution_id', sa.Integer(), nullable=False, comment='Foreign key referencing the execution (part of composite primary key)'),
        sa.Column('category_id', sa.Integer(), nullable=False, comment='Foreign key referencing the service category (part of composite primary key)'),
        sa.Column('mean_travel_time_minutes', sa.Float(), nullable=False, comment='Average travel time in minutes for this category across all city nodes'),
        sa.Column('percentage_within_threshold', sa.Float(), nullable=False, comment='Percentage of city nodes reachable within the 15-minute threshold (0-100%)'),
        sa.Column('overall_index', sa.Float(), nullable=False, comment='Consolidated reachability score used for city ranking and analysis'),
        sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['execution_id'], ['execution.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('execution_id', 'category_id')
    )

    op.create_table('node',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the node'),
        sa.Column('execution_id', sa.Integer(), nullable=False, comment='Foreign key referencing the specific execution'),
        sa.Column('osm_id', sa.BigInteger(), nullable=False, comment='Original OpenStreetMap node ID for data provenance'),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False, comment='Geographic point coordinates of the node (EPSG:4326)'),
        sa.Column('overall_index', sa.Float(), nullable=True, comment='Denormalized overall reachability index for fast map rendering'),
        sa.Column('overall_mean_time', sa.Float(), nullable=True, comment='Denormalized average travel time in minutes across all categories'),
        sa.ForeignKeyConstraint(['execution_id'], ['execution.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_node_execution_id'), 'node', ['execution_id'], unique=False)
    op.create_index(op.f('ix_node_osm_id'), 'node', ['osm_id'], unique=False)

    op.create_table('service',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='Unique primary key identifier for the service'),
        sa.Column('execution_id', sa.Integer(), nullable=False, comment='Foreign key referencing the execution'),
        sa.Column('category_id', sa.Integer(), nullable=False, comment='Foreign key referencing the service category'),
        sa.Column('representative_node_id', sa.BigInteger(), nullable=True, comment='Foreign key to the nearest network node used for Dijkstra pathfinding'),
        sa.Column('name', sa.String(length=255), nullable=True, comment='Name of the establishment from OpenStreetMap'),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False, comment='Exact geographic point coordinates of the establishment (EPSG:4326)'),
        sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['execution_id'], ['execution.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['representative_node_id'], ['node.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_category_id'), 'service', ['category_id'], unique=False)
    op.create_index(op.f('ix_service_execution_id'), 'service', ['execution_id'], unique=False)
    op.create_index(op.f('ix_service_representative_node_id'), 'service', ['representative_node_id'], unique=False)

    op.create_table('node_reachability',
        sa.Column('node_id', sa.BigInteger(), nullable=False, comment='Foreign key referencing the node (part of composite primary key)'),
        sa.Column('category_id', sa.Integer(), nullable=False, comment='Foreign key referencing the service category (part of composite primary key)'),
        sa.Column('closest_service_id', sa.BigInteger(), nullable=True, comment='Foreign key to the specific closest service establishment identified'),
        sa.Column('travel_time_minutes', sa.Float(), nullable=False, comment='Calculated walking/travel time in minutes'),
        sa.Column('within_threshold', sa.Boolean(), nullable=False, comment='Flag indicating if travel time is within the 15-minute threshold'),
        sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['closest_service_id'], ['service.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['node_id'], ['node.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('node_id', 'category_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('node_reachability')
    op.drop_index(op.f('ix_service_representative_node_id'), table_name='service')
    op.drop_index(op.f('ix_service_execution_id'), table_name='service')
    op.drop_index(op.f('ix_service_category_id'), table_name='service')
    op.drop_table('service')
    op.drop_index(op.f('ix_node_osm_id'), table_name='node')
    op.drop_index(op.f('ix_node_execution_id'), table_name='node')
    op.drop_table('node')
    op.drop_table('city_index')
    op.drop_index(op.f('ix_execution_status'), table_name='execution')
    op.drop_index(op.f('ix_execution_city_id'), table_name='execution')
    op.drop_table('execution')
    op.drop_index(op.f('ix_category_osm_tag_category_id'), table_name='category_osm_tag')
    op.drop_table('category_osm_tag')
    op.drop_index(op.f('ix_service_category_code'), table_name='service_category')
    op.drop_table('service_category')
    op.drop_index(op.f('ix_city_name'), table_name='city')
    op.drop_index(op.f('ix_city_country'), table_name='city')
    op.drop_table('city')
