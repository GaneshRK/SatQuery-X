"""Session, Image, and Query storage manager (supports in-memory store and DB)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.api.schemas import RasterMetadataResponse
from backend.geospatial.ingestion import RasterMetadata


@dataclass
class StoredImage:
    id: uuid.UUID
    session_id: uuid.UUID
    filename: str
    content_type: str
    storage_key: str
    metadata: RasterMetadata
    raw_bytes: bytes
    preview_bytes: bytes | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StoredQuery:
    id: uuid.UUID
    session_id: uuid.UUID
    text: str
    image_ids: list[uuid.UUID]
    status: str
    detected_mode: str
    task_classification: str
    trace_dict: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


@dataclass
class StoredSession:
    id: uuid.UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    images: list[StoredImage] = field(default_factory=list)
    queries: list[StoredQuery] = field(default_factory=list)


class DataStore:
    _instance = None

    def __new__(cls) -> DataStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._images = {}
            cls._instance._queries = {}
            cls._instance._reports = {}
        return cls._instance

    def create_session(self, session_id: uuid.UUID | None = None) -> StoredSession:
        sid = session_id or uuid.uuid4()
        session = StoredSession(id=sid)
        self._sessions[sid] = session
        return session

    def get_session(self, session_id: uuid.UUID) -> StoredSession | None:
        return self._sessions.get(session_id)

    def add_image(
        self,
        session_id: uuid.UUID,
        filename: str,
        content_type: str,
        storage_key: str,
        metadata: RasterMetadata,
        raw_bytes: bytes,
        preview_bytes: bytes | None = None,
        image_id: uuid.UUID | None = None,
    ) -> StoredImage:
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        iid = image_id or uuid.uuid4()
        img = StoredImage(
            id=iid,
            session_id=session_id,
            filename=filename,
            content_type=content_type,
            storage_key=storage_key,
            metadata=metadata,
            raw_bytes=raw_bytes,
            preview_bytes=preview_bytes,
        )
        session.images.append(img)
        self._images[iid] = img
        return img

    def get_image(self, image_id: uuid.UUID) -> StoredImage | None:
        return self._images.get(image_id)

    def add_query(
        self,
        session_id: uuid.UUID,
        text: str,
        image_ids: list[uuid.UUID],
        status: str,
        detected_mode: str,
        task_classification: str,
        trace_dict: dict[str, Any],
        query_id: uuid.UUID | None = None,
    ) -> StoredQuery:
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        qid = query_id or uuid.uuid4()
        query = StoredQuery(
            id=qid,
            session_id=session_id,
            text=text,
            image_ids=image_ids,
            status=status,
            detected_mode=detected_mode,
            task_classification=task_classification,
            trace_dict=trace_dict,
            completed_at=datetime.now(timezone.utc) if status == "completed" else None,
        )
        session.queries.append(query)
        self._queries[qid] = query
        return query

    def get_query(self, query_id: uuid.UUID) -> StoredQuery | None:
        return self._queries.get(query_id)

    def update_query(self, query_id: uuid.UUID, status: str, trace_dict: dict[str, Any]) -> StoredQuery | None:
        query = self._queries.get(query_id)
        if query:
            query.status = status
            query.trace_dict = trace_dict
            if status == "completed":
                query.completed_at = datetime.now(timezone.utc)
        return query

    def add_report(self, report_id: uuid.UUID, report_data: dict[str, Any]) -> None:
        self._reports[report_id] = report_data

    def get_report(self, report_id: uuid.UUID) -> dict[str, Any] | None:
        return self._reports.get(report_id)


def get_datastore() -> DataStore:
    return DataStore()
