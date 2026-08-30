"""Initial schema with PostGIS extension."""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE")),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("normalized_storage_key", sa.String(1024), nullable=True),
        sa.Column("sensor_type", sa.String(64), nullable=True),
        sa.Column("capture_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geo_referenced", sa.Boolean(), server_default="false"),
        sa.Column("crs", sa.String(64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("band_count", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image_ids", sa.JSON(), nullable=False),
        sa.Column("detected_mode", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("celery_task_id", sa.String(128), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "evidence_geometries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queries.id", ondelete="CASCADE")),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("images.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("evidence_geometries")
    op.drop_table("queries")
    op.drop_table("images")
    op.drop_table("sessions")
