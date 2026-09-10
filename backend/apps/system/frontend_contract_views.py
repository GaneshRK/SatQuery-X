"""
Frontend REST contract bridge for SatQuery-X.

This module keeps compatibility with the existing React frontend contract
while routing requests through the real Django/DRF SatQuery-X subsystems.

Design rules:
- Authentication is required for user-owned analysis data.
- No default/demo users are created automatically.
- No synthetic imagery is generated.
- No fabricated CRS, coordinates, dates, cloud cover, resolution,
  measurements, confidence, or analysis results are returned.
- Uploaded imagery is ingested through the normal imagery pipeline.
- Queries are executed through the canonical query task/orchestration path.
- User/session/project ownership is enforced.
- Password/email verification endpoints never falsely claim that an action
  happened when no delivery/verification service is configured.
"""

from __future__ import annotations
from django.contrib.auth import get_user_model
import base64
import binascii
import json
import os
import uuid
from typing import Any

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.core.files.base import ContentFile
from rest_framework import permissions, status, views
from rest_framework.response import Response
from apps.system.throttles import AnalysisRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Project
from apps.imagery.models import ImageAsset, ImagePair
from apps.imagery.tasks import ingest_image_task
from apps.queries.models import Query
from apps.queries.tasks import run_query_task
from celery import chord
from apps.sessions.models import Session

User = get_user_model()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def get_or_create_default_user():
    """
    Return a stable test/development user for internal contract tests.

    This helper is intended for test/development workflows and does not
    affect authenticated production requests.
    """
    User = get_user_model()

    user, _ = User.objects.get_or_create(
        username="satquery_test_user",
        defaults={
            "role": "demo",
            "email": "satquery_test_user@example.com",
        },
    )

    if not user.has_usable_password():
        user.set_password("password123")
        user.save(update_fields=["password"])

    return user

def _user_payload(user: User) -> dict[str, Any]:
    """Return the public frontend representation of a user."""

    return {
        "id": user.id,
        "full_name": user.get_full_name() or user.username,
        "email": user.email,
    }


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_json(value: Any) -> Any:
    """
    Parse JSON supplied either as an already-decoded object or a string.
    """

    if value is None:
        return None

    if isinstance(value, (dict, list, tuple, int, float, bool)):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    return None


def _parse_bbox(value: Any) -> list[float] | None:
    """
    Validate a GeoJSON-style numeric bbox represented as:
        [west, south, east, north]
    """

    value = _parse_json(value)

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None

    if not all(
        -180.0 <= bbox[index] <= 180.0
        for index in (0, 2)
    ):
        return None

    if not all(
        -90.0 <= bbox[index] <= 90.0
        for index in (1, 3)
    ):
        return None

    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return None

    return bbox


def _decode_base64_file(
    value: Any,
    filename: str,
) -> ContentFile | None:
    """
    Convert a data URL/base64 payload into a Django ContentFile.

    This function performs no scientific interpretation of the bytes.
    """

    if not isinstance(value, str) or not value.strip():
        return None

    encoded = value.strip()

    if "," in encoded:
        header, encoded = encoded.split(",", 1)

        # Reject obvious non-image data URLs when a MIME type is supplied.
        if header.lower().startswith("data:"):
            mime = header[5:].split(";", 1)[0].lower()
            if mime and not mime.startswith("image/"):
                return None

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, binascii.Error):
        return None

    if not raw:
        return None

    return ContentFile(raw, name=filename)


def _file_format(filename: str) -> str:
    """
    Determine a storage/display format from the filename extension only.

    This is not a georeferencing claim.
    """

    extension = os.path.splitext(filename or "")[1].lower()

    mapping = {
        ".tif": "GEOTIFF",
        ".tiff": "GEOTIFF",
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
        ".bmp": "BMP",
    }

    return mapping.get(extension, "UNKNOWN")


def _request_sensor(request) -> str:
    value = _normalise_text(request.data.get("source"))
    return value.upper() if value else "UNKNOWN"


def _request_date(value: Any):
    """
    Preserve an acquisition date only when it is explicitly supplied and
    parseable by Django's DateField.
    """

    from datetime import date

    text = _normalise_text(value)

    if not text:
        return None

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _asset_file_url(asset: ImageAsset) -> str | None:
    try:
        file_obj = getattr(asset, "file", None)
        if file_obj and getattr(file_obj, "url", None):
            return str(file_obj.url)
    except Exception:
        pass
    return None


def _asset_summary(asset: ImageAsset) -> dict[str, Any]:
    """
    Return actual stored imagery metadata.

    Missing scientific metadata remains None.
    """

    return {
        "id": str(asset.id),
        "filename": (
            getattr(asset, "original_filename", None)
            or getattr(asset.file, "name", None)
            or ""
        ),
        "sensor": getattr(asset, "sensor", None),
        "modality": getattr(asset, "modality", None),
        "processing_status": getattr(
            asset,
            "processing_status",
            None,
        ),
        "acquisition_date": (
            asset.acquisition_date.isoformat()
            if getattr(asset, "acquisition_date", None)
            else None
        ),
        "is_georeferenced": getattr(
            asset,
            "is_georeferenced",
            None,
        ),
        "crs": getattr(asset, "crs", None),
        "resolution_m": getattr(asset, "resolution_m", None),
        "cloud_cover_pct": getattr(
            asset,
            "cloud_cover_pct",
            None,
        ),
        "bounds_wgs84": getattr(
            asset,
            "bounds_wgs84",
            None,
        ),
        # Real browser-openable media URLs. These are derived from Django
        # storage; no temporary blob URL is persisted as the scientific
        # result.
        "file_url": _asset_file_url(asset),
        "preview_url": getattr(asset, "preview_url", None),
    }


def _pair_summary(pair: ImagePair | None) -> dict[str, Any] | None:
    if pair is None:
        return None

    return {
        "id": str(pair.id),
        "pair_type": getattr(pair, "pair_type", None),
        "compatibility_status": getattr(
            pair,
            "compatibility_status",
            None,
        ),
        "coregistration_status": getattr(
            pair,
            "coregistration_status",
            None,
        ),
        "image_a_id": str(pair.image_a_id),
        "image_b_id": str(pair.image_b_id),
    }


def _query_response(
    query: Query,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Return a compatibility response without manufacturing analysis output.
    """

    assets = []
    try:
        assets = list(query.input_assets.all())
    except Exception:
        if query.image is not None:
            assets = [query.image]

    payload: dict[str, Any] = {
        "analysis_id": str(query.id),
        "query_id": str(query.id),
        "status": query.status,
        "query": query.text,
        "answer": query.answer,
        "confidence": query.confidence,
        "error": getattr(query, "error", None),
        "detected_mode": query.detected_mode,
        "detected_task": query.detected_task,
        "completed_at": (query.completed_at.isoformat() if getattr(query, "completed_at", None) else None),
        "images": [
            _asset_summary(asset)
            for asset in assets
        ],
        "clarification_required": getattr(
            query,
            "clarification_required",
            False,
        ),
        "clarification": getattr(
            query,
            "clarification",
            None,
        ),
        "plan": query.plan,
        "evidence_graph": query.evidence_graph,
        "evidence_bundle": getattr(
            query,
            "evidence_bundle",
            {},
        ),
        "answer_trace": getattr(
            query,
            "answer_trace",
            [],
        ),
    }

    if task_id:
        payload["task_id"] = task_id

    return payload


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class ContractRegisterView(views.APIView):
    """
    POST /api/auth/register/

    Creates a real Django user and returns JWT credentials.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = _normalise_text(
            request.data.get("email")
        ).lower()
        password = request.data.get("password", "")
        full_name = _normalise_text(
            request.data.get("full_name")
        )

        if not email or not password:
            return Response(
                {
                    "error": "Email and password are required.",
                    "detail": "Email and password are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(password) < 8:
            return Response(
                {
                    "error": "Password must contain at least 8 characters.",
                    "detail": "Password must contain at least 8 characters.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(
            email__iexact=email
        ).exists():
            return Response(
                {
                    "error": "An account with this email already exists.",
                    "detail": "An account with this email already exists.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        username_base = (
            email.split("@", 1)[0]
            or f"user_{uuid.uuid4().hex[:8]}"
        )

        username = username_base

        while User.objects.filter(
            username=username
        ).exists():
            username = (
                f"{username_base}_{uuid.uuid4().hex[:6]}"
            )

        name_parts = full_name.split(" ", 1)

        first_name = name_parts[0] if name_parts else ""
        last_name = (
            name_parts[1]
            if len(name_parts) > 1
            else ""
        )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role="ANALYST",
        )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": _user_payload(user),
            },
            status=status.HTTP_201_CREATED,
        )


class ContractLoginView(views.APIView):
    """
    POST /api/auth/login/

    Authenticates against the actual Django user database.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = _normalise_text(
            request.data.get("email")
        ).lower()
        username = _normalise_text(
            request.data.get("username")
        )
        password = request.data.get("password", "")

        user = None

        if email:
            candidate = (
                User.objects
                .filter(email__iexact=email)
                .first()
            )

            if candidate and candidate.check_password(password):
                user = candidate

        if user is None:
            user = authenticate(
                request=request,
                username=username or email,
                password=password,
            )

        if user is None:
            return Response(
                {
                    "error": "Invalid email or password.",
                    "detail": "Invalid email or password.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {
                    "error": "This account is inactive.",
                    "detail": "This account is inactive.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": _user_payload(user),
            },
            status=status.HTTP_200_OK,
        )


class ContractMeView(views.APIView):
    """
    GET /api/auth/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(
            _user_payload(request.user),
            status=status.HTTP_200_OK,
        )


class ContractForgotPasswordView(views.APIView):
    """
    Password reset compatibility endpoint.

    A real email/SMS delivery provider must be configured before this
    endpoint can honestly claim that a reset message was sent.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = _normalise_text(
            request.data.get("email")
        ).lower()

        if not email:
            return Response(
                {
                    "error": "Email is required.",
                    "detail": "Email is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Do not reveal whether an account exists.
        # No external reset-delivery service is assumed here.
        return Response(
            {
                "message": (
                    "Password reset delivery is not configured. "
                    "No reset message was sent."
                ),
                "configured": False,
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class ContractVerifyEmailView(views.APIView):
    """
    Email verification compatibility endpoint.

    Verification must be implemented through a real verification-token
    workflow before an account can be marked verified.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        return Response(
            {
                "message": (
                    "Email verification is not configured. "
                    "The account was not marked as verified."
                ),
                "verified": False,
                "configured": False,
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class ContractAnalysisQueryView(views.APIView):
    """
    POST /api/analysis/query/

    Compatibility bridge for the existing frontend analysis contract.

    Supported inputs include:

    - query
    - location
    - source
    - start_date
    - end_date
    - bbox
    - image / file
    - before_image / image_before
    - after_image / image_after
    - optical_image
    - sar_image
    - image_base64
    - before_image_base64
    - after_image_base64

    The bridge creates real ImageAsset records and sends the query through
    the canonical SatQuery-X query task.

    It never assigns georeferencing or scientific metadata merely because
    the frontend supplied a location or date range.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisRateThrottle]

    def _get_or_create_session(
        self,
        request,
    ) -> Session:
        """
        Reuse an explicitly supplied authenticated session when possible;
        otherwise create a normal workspace session.
        """

        requested_id = _normalise_text(
            request.data.get("session_id")
        )

        if requested_id:
            session = (
                Session.objects
                .filter(
                    id=requested_id,
                    user=request.user,
                )
                .first()
            )

            if session is None:
                raise ValueError(
                    "The requested session does not exist "
                    "or does not belong to the authenticated user."
                )

            return session

        session = (
            Session.objects
            .filter(
                user=request.user,
                status="active",
            )
            .order_by("-updated_at")
            .first()
        )

        if session is not None:
            return session

        return Session.objects.create(
            user=request.user,
            name="SatQuery-X Analysis Workspace",
        )

    def _create_asset(
        self,
        *,
        session: Session,
        file_obj,
        modality: str = "UNKNOWN",
        sensor: str = "UNKNOWN",
        acquisition_date=None,
    ) -> ImageAsset:
        """
        Create an asset without claiming that it is georeferenced or
        scientifically calibrated.
        """

        filename = (
            getattr(file_obj, "name", None)
            or "uploaded_image"
        )

        return ImageAsset.objects.create(
            session=session,
            file=file_obj,
            original_filename=filename,
            file_format=_file_format(filename),
            sensor=sensor or "UNKNOWN",
            modality=modality or "UNKNOWN",
            acquisition_date=acquisition_date,
            processing_status="PENDING",
            is_georeferenced=False,
        )

    def _ingest_asset(self, asset: ImageAsset) -> None:
        """
        Queue normal imagery ingestion.

        The ingestion worker is responsible for discovering real metadata.
        """

        ingest_image_task.delay(str(asset.id))

    def _update_session_context(
        self,
        session: Session,
        *,
        location: str | None,
        bbox: list[float] | None,
        source: str,
        start_date: Any,
        end_date: Any,
        assets: list[ImageAsset],
    ) -> None:
        context = dict(
            getattr(
                session,
                "conversation_context",
                {},
            )
            or {}
        )

        if bbox:
            context["current_viewport"] = {
                "west": bbox[0],
                "south": bbox[1],
                "east": bbox[2],
                "north": bbox[3],
            }

        if location:
            # Location text is context, not fabricated geospatial geometry.
            context["active_location"] = location

        if start_date or end_date:
            context["time_range"] = {
                "start": start_date,
                "end": end_date,
            }

        if source:
            context["requested_sensor"] = source.upper()

        context["input_asset_ids"] = [
            str(asset.id)
            for asset in assets
        ]

        context["has_images"] = bool(assets)
        context["image_count"] = len(assets)

        session.conversation_context = context

        session.save(
            update_fields=["conversation_context"]
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        query_text = _normalise_text(
            request.data.get("query")
        )

        if not query_text:
            return Response(
                {
                    "error": "Query text cannot be empty.",
                    "detail": "Query text cannot be empty.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = self._get_or_create_session(request)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        location = _normalise_text(
            request.data.get("location")
        ) or None

        source = _request_sensor(request)

        start_date_raw = _normalise_text(
            request.data.get("start_date")
        )
        end_date_raw = _normalise_text(
            request.data.get("end_date")
        )

        bbox = _parse_bbox(
            request.data.get("bbox")
        )

        before_file = (
            request.FILES.get("before_image")
            or request.FILES.get("image_before")
        )

        after_file = (
            request.FILES.get("after_image")
            or request.FILES.get("image_after")
        )

        optical_file = request.FILES.get(
            "optical_image"
        )

        sar_file = request.FILES.get(
            "sar_image"
        )

        single_file = (
            request.FILES.get("image")
            or request.FILES.get("file")
        )

        if before_file is None:
            before_file = _decode_base64_file(
                request.data.get(
                    "before_image_base64"
                ),
                "before_image",
            )

        if after_file is None:
            after_file = _decode_base64_file(
                request.data.get(
                    "after_image_base64"
                ),
                "after_image",
            )

        if single_file is None:
            single_file = _decode_base64_file(
                request.data.get(
                    "image_base64"
                ),
                "uploaded_image",
            )

        assets: list[ImageAsset] = []

        if before_file and after_file:
            before_asset = self._create_asset(
                session=session,
                file_obj=before_file,
                modality="OPTICAL",
                sensor=source,
                acquisition_date=_request_date(
                    start_date_raw
                ),
            )

            after_asset = self._create_asset(
                session=session,
                file_obj=after_file,
                modality="OPTICAL",
                sensor=source,
                acquisition_date=_request_date(
                    end_date_raw
                ),
            )

            assets.extend(
                [
                    before_asset,
                    after_asset,
                ]
            )

        elif optical_file and sar_file:
            optical_asset = self._create_asset(
                session=session,
                file_obj=optical_file,
                modality="OPTICAL",
                sensor="UNKNOWN",
                acquisition_date=_request_date(
                    start_date_raw
                ),
            )

            sar_asset = self._create_asset(
                session=session,
                file_obj=sar_file,
                modality="SAR",
                sensor="UNKNOWN",
                acquisition_date=_request_date(
                    start_date_raw
                ),
            )

            assets.extend(
                [
                    optical_asset,
                    sar_asset,
                ]
            )

        elif single_file:
            single_asset = self._create_asset(
                session=session,
                file_obj=single_file,
                modality="UNKNOWN",
                sensor=source,
                acquisition_date=_request_date(
                    start_date_raw
                ),
            )

            assets.append(single_asset)

        elif any(
            value is not None
            for value in (
                before_file,
                after_file,
                optical_file,
                sar_file,
            )
        ):
            return Response(
                {
                    "error": (
                        "The supplied imagery inputs do not form a "
                        "supported image request."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._update_session_context(
            session,
            location=location,
            bbox=bbox,
            source=source,
            start_date=start_date_raw or None,
            end_date=end_date_raw or None,
            assets=assets,
        )

        query_obj = Query.objects.create(
            session=session,
            user=request.user,
            text=query_text,
            image=assets[0] if assets else None,
        )

        # Store all uploaded assets when the current model supports the
        # normalized many-to-many input relationship.
        if assets and hasattr(
            query_obj,
            "input_assets",
        ):
            query_obj.input_assets.set(assets)

        pair = None

        if len(assets) == 2:
            requested_pair_type = (
                "CROSS_MODAL"
                if (
                    assets[0].modality == "OPTICAL"
                    and assets[1].modality == "SAR"
                )
                or (
                    assets[0].modality == "SAR"
                    and assets[1].modality == "OPTICAL"
                )
                else "BI_TEMPORAL"
            )

            # Do NOT mark a pair compatible here.
            # Compatibility must be established by the imagery pipeline.
            existing_pair = (
                ImagePair.objects
                .filter(
                    session=session,
                    image_a=assets[0],
                    image_b=assets[1],
                    pair_type=requested_pair_type,
                )
                .first()
            )

            if existing_pair is None:
                existing_pair = (
                    ImagePair.objects
                    .filter(
                        session=session,
                        image_a=assets[1],
                        image_b=assets[0],
                        pair_type=requested_pair_type,
                    )
                    .first()
                )

            if existing_pair is not None:
                pair = existing_pair
                query_obj.image_pair = pair

        if pair is not None:
            query_obj.save(
                update_fields=["image_pair"]
            )

        # Queue ingestion first. The analysis MUST start only after every
        # uploaded asset has completed ingestion; otherwise the query worker
        # can race the ingestion worker and see an unvalidated image.
        try:
            if assets:
                ingestion_jobs = [
                    ingest_image_task.s(str(asset.id))
                    for asset in assets
                ]
                task_result = chord(ingestion_jobs)(
                    run_query_task.s(str(query_obj.id))
                )
            else:
                task_result = run_query_task.delay(
                    str(query_obj.id)
                )

            query_obj.refresh_from_db()

            response_payload = _query_response(
                query_obj,
                task_id=str(task_result.id),
            )

            response_payload.update(
                {
                    "workflow": query_obj.detected_mode,
                    "session_id": str(session.id),
                    "image_ids": [
                        str(asset.id)
                        for asset in assets
                    ],
                    "pair_id": (
                        str(pair.id)
                        if pair is not None
                        else None
                    ),
                    "queued": True,
                }
            )

            return Response(
                response_payload,
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as exc:
            query_obj.refresh_from_db()

            return Response(
                {
                    **_query_response(query_obj),
                    "session_id": str(session.id),
                    "image_ids": [
                        str(asset.id)
                        for asset in assets
                    ],
                    "pair_id": (
                        str(pair.id)
                        if pair is not None
                        else None
                    ),
                    "queued": False,
                    "error": (
                        "The analysis could not be queued."
                    ),
                    "detail": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


# ---------------------------------------------------------------------------
# Analysis history/detail
# ---------------------------------------------------------------------------


class ContractAnalysisHistoryView(views.APIView):
    """
    GET /api/analysis/history/

    Returns only the authenticated user's analysis history.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queries = (
            Query.objects
            .filter(session__user=request.user)
            .order_by("-created_at")[:20]
        )

        history = []

        for query in queries:
            answer = query.answer or ""

            history.append(
                {
                    "analysis_id": str(query.id),
                    "query_id": str(query.id),
                    "query": query.text,
                    "answer": (
                        answer[:250] + "..."
                        if len(answer) > 250
                        else answer
                    ),
                    "confidence": query.confidence,
                    "status": query.status,
                    "clarification_required": getattr(
                        query,
                        "clarification_required",
                        False,
                    ),
                    "created_at": (
                        query.created_at.isoformat()
                        if query.created_at
                        else ""
                    ),
                    "completed_at": (
                        query.completed_at.isoformat()
                        if getattr(
                            query,
                            "completed_at",
                            None,
                        )
                        else None
                    ),
                }
            )

        return Response(
            history,
            status=status.HTTP_200_OK,
        )


class ContractAnalysisDetailView(views.APIView):
    """
    GET /api/analysis/<pk>/

    Returns a query only when it belongs to the authenticated user.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        query_obj = (
            Query.objects
            .filter(
                id=pk,
                session__user=request.user,
            )
            .first()
        )

        if query_obj is None:
            return Response(
                {
                    "error": "Analysis not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            _query_response(query_obj),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ContractProjectListCreateView(views.APIView):
    """
    Compatibility bridge for project management.

    Project ownership is enforced using the actual project/session model
    relationships where available.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = Project.objects.all()

        # Prefer an explicit user relationship when the model provides one.
        field_names = {
            field.name
            for field in Project._meta.get_fields()
        }

        if "user" in field_names:
            queryset = queryset.filter(
                user=request.user
            )
        elif "owner" in field_names:
            queryset = queryset.filter(
                owner=request.user
            )
        elif "created_by" in field_names:
            queryset = queryset.filter(
                created_by=request.user
            )
        else:
            # If the Project model has no ownership relation, do not expose
            # the entire project table to an authenticated user.
            queryset = queryset.none()

        projects = queryset.order_by(
            "-created_at"
        )[:15]

        return Response(
            [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "description": project.description,
                    "created_at": (
                        project.created_at.isoformat()
                        if project.created_at
                        else ""
                    ),
                }
                for project in projects
            ],
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        name = _normalise_text(
            request.data.get("name")
        )

        description = _normalise_text(
            request.data.get("description")
        )

        if not name:
            return Response(
                {
                    "error": "Project name is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        field_names = {
            field.name
            for field in Project._meta.get_fields()
        }

        project_kwargs: dict[str, Any] = {
            "name": name,
            "description": description,
        }

        if "user" in field_names:
            project_kwargs["user"] = request.user
        elif "owner" in field_names:
            project_kwargs["owner"] = request.user
        elif "created_by" in field_names:
            project_kwargs["created_by"] = request.user
        else:
            return Response(
                {
                    "error": (
                        "Project ownership is not configured for "
                        "the current backend model."
                    )
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        project = Project.objects.create(
            **project_kwargs
        )

        return Response(
            {
                "id": str(project.id),
                "name": project.name,
                "description": project.description,
                "created_at": (
                    project.created_at.isoformat()
                    if project.created_at
                    else ""
                ),
            },
            status=status.HTTP_201_CREATED,
        )