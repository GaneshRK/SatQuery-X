"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from enum import Enum

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class InputMode(str, Enum):
    SINGLE_IMAGE = "single_image"
    CROSS_MODAL_PAIR = "cross_modal_pair"
    BI_TEMPORAL = "bi_temporal"
    CHANGE_VQA = "change_vqa"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    images: Mapped[list["ImageRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    queries: Mapped[list["QueryRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ImageRecord(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_key: Mapped[str] = mapped_column(String(1024))
    normalized_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sensor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capture_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    geo_referenced: Mapped[bool] = mapped_column(default=False)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    band_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="images")
    evidence_items: Mapped[list["EvidenceGeometry"]] = relationship(back_populates="image")


class QueryRecord(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    image_ids: Mapped[list] = mapped_column(JSON)
    detected_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="queries")


class EvidenceGeometry(Base):
    __tablename__ = "evidence_geometries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    image_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(64))
    geometry: Mapped[object] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326))
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    image: Mapped["ImageRecord | None"] = relationship(back_populates="evidence_items")
