"""
Imagery artifact registry and response DTOs.

Responsibilities
----------------
- Register only artifacts that actually exist.
- Preserve provenance from ImageAsset.
- Generate browser previews from real imagery when required.
- Never invent satellite metadata, coordinates, dates, cloud cover,
  resolution, sensor names, or scientific measurements.
- Keep URLs compatible with Django/DRF responses.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction

from apps.imagery.models import (
    ImageAsset,
    ImageryArtifact,
)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class ImageryArtifactDTO:
    """
    API-facing representation of an imagery asset.

    All scientific metadata is optional because uploaded imagery may not
    contain complete metadata.
    """

    id: str

    date: Optional[str] = None
    satellite: Optional[str] = None
    product: Optional[str] = None
    source: Optional[str] = None

    geotiff_url: Optional[str] = None
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    bounds: Optional[List[float]] = None
    cloud_cover_pct: Optional[float] = None
    resolution_m: Optional[float] = None

    preview_path: Optional[str] = None
    thumbnail_path: Optional[str] = None

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert DTO to a JSON-serializable dictionary.
        """

        return asdict(self)


@dataclass
class AnalysisArtifactDTO:
    """
    API-facing representation of analysis outputs.

    Every URL is optional because an analysis may produce only some
    derivatives.
    """

    change_mask_url: Optional[str] = None
    change_mask_geotiff_url: Optional[str] = None
    change_geojson_url: Optional[str] = None
    evidence_json_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def make_absolute_url(
    path_or_url: Optional[str],
    request: Optional[Any] = None,
) -> Optional[str]:
    """
    Convert a storage/media path into an absolute URL when possible.

    Priority:
        1. Existing absolute URL
        2. Django request origin
        3. Configured API_HOST
        4. Relative path

    No fictional/default scientific information is introduced here.
    """

    if not path_or_url:
        return None

    value = str(
        path_or_url
    ).strip()

    if not value:
        return None

    if value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return value

    # Ensure a leading slash.
    if not value.startswith("/"):
        media_url = str(
            getattr(
                settings,
                "MEDIA_URL",
                "/media/",
            )
        )

        if media_url.endswith("/"):
            value = (
                media_url
                + value.lstrip("/")
            )
        else:
            value = (
                media_url
                + "/"
                + value.lstrip("/")
            )

    if request is not None:
        try:
            return request.build_absolute_uri(
                value
            )
        except Exception:
            pass

    api_host = getattr(
        settings,
        "API_HOST",
        None,
    )

    if api_host:
        return (
            str(api_host).rstrip("/")
            + "/"
            + value.lstrip("/")
        )

    # Returning the relative URL is preferable to inventing a host.
    return value


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _storage_name_from_path(
    path: Optional[str],
) -> Optional[str]:
    """
    Convert a local MEDIA_ROOT path into a Django storage-relative name.

    If the supplied path is already a storage name, it is preserved.
    """

    if not path:
        return None

    raw = str(
        path
    ).strip()

    if not raw:
        return None

    normalized = raw.replace(
        "\\",
        "/",
    )

    media_root = getattr(
        settings,
        "MEDIA_ROOT",
        "",
    )

    if media_root:
        try:
            absolute_media_root = os.path.abspath(
                media_root
            )

            absolute_path = os.path.abspath(
                raw
            )

            relative = os.path.relpath(
                absolute_path,
                absolute_media_root,
            )

            if not relative.startswith(
                ".."
            ):
                return relative.replace(
                    "\\",
                    "/",
                )
        except (
            OSError,
            ValueError,
        ):
            pass

    media_url = str(
        getattr(
            settings,
            "MEDIA_URL",
            "/media/",
        )
    )

    if normalized.startswith(
        media_url
    ):
        return normalized[
            len(media_url):
        ].lstrip("/")

    return normalized.lstrip("/")


def _resolve_local_path(
    path: Optional[str],
) -> Optional[str]:
    """
    Resolve a generated artifact path on local storage.

    Returns None when the path does not exist locally.
    """

    if not path:
        return None

    raw = str(
        path
    ).strip()

    if not raw:
        return None

    if os.path.isfile(
        raw
    ):
        return raw

    media_root = getattr(
        settings,
        "MEDIA_ROOT",
        None,
    )

    if not media_root:
        return None

    relative = _storage_name_from_path(
        raw
    )

    if not relative:
        return None

    candidate = os.path.join(
        media_root,
        relative,
    )

    if os.path.isfile(
        candidate
    ):
        return candidate

    return None


def _storage_url(
    storage_name: Optional[str],
) -> Optional[str]:
    """
    Get the URL for a Django storage object.
    """

    if not storage_name:
        return None

    try:
        if not default_storage.exists(
            storage_name
        ):
            return None

        return default_storage.url(
            storage_name
        )
    except Exception:
        return None


def _register_file_in_storage(
    local_path: str,
    preferred_name: str,
) -> Optional[str]:
    """
    Register a generated local file with Django's configured storage.

    Returns the storage-relative filename.
    """

    if not local_path:
        return None

    if not os.path.isfile(
        local_path
    ):
        return None

    try:
        with open(
            local_path,
            "rb",
        ) as handle:

            stored_name = default_storage.save(
                preferred_name,
                File(handle),
            )

        return stored_name

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def _safe_float(
    value: Any,
) -> Optional[float]:
    if value is None:
        return None

    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if number != number:
        return None

    if number in (
        float("inf"),
        float("-inf"),
    ):
        return None

    return number


def _extract_provenance(
    image_asset: ImageAsset,
) -> Dict[str, Any]:
    """
    Return provenance without inventing missing fields.
    """

    provenance = (
        image_asset.provenance
        if isinstance(
            image_asset.provenance,
            dict,
        )
        else {}
    )

    return dict(
        provenance
    )


def _get_provenance_value(
    provenance: Dict[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first non-empty provenance field.
    """

    for key in keys:
        value = provenance.get(
            key
        )

        if value not in (
            None,
            "",
            [],
            {},
        ):
            return value

    return None


def _serialize_bounds(
    bounds: Any,
) -> Optional[List[float]]:
    """
    Preserve actual WGS84 bounds when available.

    Does not create default coordinates.
    """

    if bounds is None:
        return None

    if isinstance(
        bounds,
        dict,
    ):
        west = _safe_float(
            bounds.get(
                "west"
            )
        )

        south = _safe_float(
            bounds.get(
                "south"
            )
        )

        east = _safe_float(
            bounds.get(
                "east"
            )
        )

        north = _safe_float(
            bounds.get(
                "north"
            )
        )

        if None in (
            west,
            south,
            east,
            north,
        ):
            return None

        return [
            west,
            south,
            east,
            north,
        ]

    if isinstance(
        bounds,
        (
            list,
            tuple,
        )
    ):
        if len(bounds) != 4:
            return None

        values = [
            _safe_float(
                item
            )
            for item in bounds
        ]

        if any(
            item is None
            for item in values
        ):
            return None

        return values

    return None


def _asset_metadata(
    image_asset: ImageAsset,
) -> Dict[str, Any]:
    """
    Build a metadata object containing only information actually present
    on the ImageAsset.
    """

    provenance = _extract_provenance(
        image_asset
    )

    metadata: Dict[str, Any] = {}

    fields = {
        "sensor":
            getattr(
                image_asset,
                "sensor",
                None,
            ),

        "modality":
            getattr(
                image_asset,
                "modality",
                None,
            ),

        "acquisition_date":
            getattr(
                image_asset,
                "acquisition_date",
                None,
            ),

        "width":
            getattr(
                image_asset,
                "width",
                None,
            ),

        "height":
            getattr(
                image_asset,
                "height",
                None,
            ),

        "band_count":
            getattr(
                image_asset,
                "band_count",
                None,
            ),

        "dtype":
            getattr(
                image_asset,
                "dtype",
                None,
            ),

        "resolution_m":
            getattr(
                image_asset,
                "resolution_m",
                None,
            ),

        "cloud_cover_pct":
            getattr(
                image_asset,
                "cloud_cover_pct",
                None,
            ),

        "crs":
            getattr(
                image_asset,
                "crs",
                None,
            ),

        "bounds_wgs84":
            getattr(
                image_asset,
                "bounds_wgs84",
                None,
            ),
    }

    for key, value in fields.items():
        if value is not None:
            metadata[key] = value

    # Provenance is itself evidence and should be preserved.
    if provenance:
        metadata[
            "provenance"
        ] = provenance

    return metadata


# ---------------------------------------------------------------------------
# Artifact creation helpers
# ---------------------------------------------------------------------------

def _get_existing_artifact(
    image_asset: ImageAsset,
    artifact_type: str,
) -> Optional[ImageryArtifact]:
    """
    Safely fetch the first artifact of a specific type.
    """

    return (
        image_asset.artifacts
        .filter(
            artifact_type=artifact_type
        )
        .first()
    )


def _artifact_url(
    artifact: Optional[ImageryArtifact],
) -> Optional[str]:
    """
    Resolve an artifact's storage URL.
    """

    if not artifact:
        return None

    try:
        if artifact.file:
            return artifact.file.url
    except Exception:
        pass

    return None


def _artifact_local_path(
    artifact: Optional[ImageryArtifact],
) -> Optional[str]:
    """
    Resolve local filesystem path when supported by storage.
    """

    if not artifact:
        return None

    try:
        if artifact.file:
            path = artifact.file.path

            if os.path.isfile(
                path
            ):
                return path
    except Exception:
        pass

    return None


def _artifact_dimensions(
    image_asset: ImageAsset,
) -> Dict[str, Optional[int]]:
    """
    Return actual asset dimensions.

    Missing values remain None.
    """

    return {
        "width":
        getattr(
            image_asset,
            "width",
            None,
        ),

        "height":
        getattr(
            image_asset,
            "height",
            None,
        ),
    }


def _create_or_update_artifact(
    *,
    image_asset: ImageAsset,
    artifact_type: str,
    storage_name: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> Optional[ImageryArtifact]:
    """
    Create/update an ImageryArtifact only when an actual file is available.
    """

    if not storage_name:
        return None

    if not default_storage.exists(
        storage_name
    ):
        return None

    dimensions = _artifact_dimensions(
        image_asset
    )

    bounds = _serialize_bounds(
        getattr(
            image_asset,
            "bounds_wgs84",
            None,
        )
    )

    defaults: Dict[str, Any] = {
        "mime_type":
        mime_type,

        "width":
        dimensions["width"],

        "height":
        dimensions["height"],

        "bounds":
        bounds,
    }

    # Do not overwrite valid mime type with None.
    if mime_type is None:
        defaults.pop(
            "mime_type",
            None,
        )

    artifact, created = (
        ImageryArtifact.objects.get_or_create(
            image_asset=image_asset,
            artifact_type=artifact_type,
            defaults=defaults,
        )
    )

    if not created:
        update_fields = []

        if mime_type is not None:
            artifact.mime_type = mime_type
            update_fields.append(
                "mime_type"
            )

        if dimensions["width"] is not None:
            artifact.width = dimensions[
                "width"
            ]
            update_fields.append(
                "width"
            )

        if dimensions["height"] is not None:
            artifact.height = dimensions[
                "height"
            ]
            update_fields.append(
                "height"
            )

        if bounds is not None:
            artifact.bounds = bounds
            update_fields.append(
                "bounds"
            )

        # Only update the file when necessary.
        try:
            if not artifact.file:
                artifact.file.name = storage_name
                update_fields.append(
                    "file"
                )
        except Exception:
            artifact.file.name = storage_name
            update_fields.append(
                "file"
            )

        if update_fields:
            artifact.save(
                update_fields=list(
                    dict.fromkeys(
                        update_fields
                    )
                )
            )

    return artifact


# ---------------------------------------------------------------------------
# Preview generation
# ---------------------------------------------------------------------------

def _generate_preview_if_required(
    image_asset: ImageAsset,
) -> Tuple[
    Optional[str],
    Optional[str],
]:
    """
    Generate preview and thumbnail from the actual ImageAsset file.

    Returns:
        local preview path,
        local thumbnail path

    If the source cannot be decoded, the exception is propagated. A fake
    image is never generated.
    """

    from apps.imagery.services.preview import (
        generate_rgb_preview,
    )

    # Existing preview artifact.
    existing_preview = _get_existing_artifact(
        image_asset,
        "RGB_PREVIEW",
    )

    existing_thumbnail = _get_existing_artifact(
        image_asset,
        "THUMBNAIL",
    )

    existing_preview_path = (
        _artifact_local_path(
            existing_preview
        )
    )

    existing_thumbnail_path = (
        _artifact_local_path(
            existing_thumbnail
        )
    )

    if (
        existing_preview_path
        and existing_thumbnail_path
    ):
        return (
            existing_preview_path,
            existing_thumbnail_path,
        )

    # Resolve actual source file.
    source_path = None

    try:
        if image_asset.file:
            source_path = image_asset.file.path
    except Exception:
        source_path = None

    if not source_path:
        raise ValueError(
            (
                "Cannot generate imagery preview because the "
                "source file has no local filesystem path."
            )
        )

    if not os.path.isfile(
        source_path
    ):
        raise FileNotFoundError(
            (
                "Cannot generate imagery preview because the "
                "source imagery file does not exist."
            )
        )

    media_root = getattr(
        settings,
        "MEDIA_ROOT",
        None,
    )

    if not media_root:
        raise RuntimeError(
            "MEDIA_ROOT is not configured."
        )

    previews_dir = os.path.join(
        media_root,
        "previews",
    )

    os.makedirs(
        previews_dir,
        exist_ok=True,
    )

    preview_path = os.path.join(
        previews_dir,
        f"{image_asset.id}_rgb.webp",
    )

    thumbnail_path = os.path.join(
        previews_dir,
        f"{image_asset.id}_thumb.webp",
    )

    generate_rgb_preview(
        source_path,
        preview_path,
        thumbnail_path,
    )

    if not os.path.isfile(
        preview_path
    ):
        raise RuntimeError(
            "Preview generation completed without producing a preview file."
        )

    if not os.path.isfile(
        thumbnail_path
    ):
        raise RuntimeError(
            "Preview generation completed without producing a thumbnail."
        )

    return (
        preview_path,
        thumbnail_path,
    )


# ---------------------------------------------------------------------------
# Main artifact registration
# ---------------------------------------------------------------------------

@transaction.atomic
def register_imagery_artifacts(
    image_asset: ImageAsset,
    preview_file_path: Optional[str] = None,
    thumbnail_file_path: Optional[str] = None,
    *,
    request: Optional[Any] = None,
    generate_preview: bool = True,
) -> ImageryArtifactDTO:
    """
    Register actual imagery derivatives for an ImageAsset.

    Scientific source
    -----------------
    The ImageAsset's uploaded file remains the source of truth.

    Derived artifacts
    -----------------
    - GEOTIFF: only if the source asset file exists.
    - RGB_PREVIEW: only if an actual preview exists or can be generated.
    - THUMBNAIL: only if an actual thumbnail exists or can be generated.

    No metadata fallback values are created.
    """

    if image_asset is None:
        raise ValueError(
            "image_asset is required."
        )

    provenance = _extract_provenance(
        image_asset
    )

    # ------------------------------------------------------------------
    # 1. Scientific source artifact
    # ------------------------------------------------------------------

    geotiff_artifact = None

    source_storage_name = None

    try:
        if image_asset.file:
            source_storage_name = (
                image_asset.file.name
            )
    except Exception:
        source_storage_name = None

    if source_storage_name:
        mime_type = (
            "image/tiff"
        )

        filename = str(
            source_storage_name
        ).lower()

        if filename.endswith(
            (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            )
        ):
            mime_type = {
                ".png":
                "image/png",

                ".jpg":
                "image/jpeg",

                ".jpeg":
                "image/jpeg",

                ".webp":
                "image/webp",
            }.get(
                Path(
                    filename
                ).suffix,
                "application/octet-stream",
            )

        geotiff_artifact = (
            _create_or_update_artifact(
                image_asset=image_asset,
                artifact_type="GEOTIFF",
                storage_name=source_storage_name,
                mime_type=mime_type,
            )
        )

    # ------------------------------------------------------------------
    # 2. Resolve or generate visual derivatives
    # ------------------------------------------------------------------

    if generate_preview:
        if not preview_file_path or not os.path.isfile(
            preview_file_path
        ):
            existing_preview = (
                _get_existing_artifact(
                    image_asset,
                    "RGB_PREVIEW",
                )
            )

            existing_preview_path = (
                _artifact_local_path(
                    existing_preview
                )
            )

            if existing_preview_path:
                preview_file_path = (
                    existing_preview_path
                )

        if not thumbnail_file_path or not os.path.isfile(
            thumbnail_file_path
        ):
            existing_thumbnail = (
                _get_existing_artifact(
                    image_asset,
                    "THUMBNAIL",
                )
            )

            existing_thumbnail_path = (
                _artifact_local_path(
                    existing_thumbnail
                )
            )

            if existing_thumbnail_path:
                thumbnail_file_path = (
                    existing_thumbnail_path
                )

        if (
            not preview_file_path
            or not os.path.isfile(
                preview_file_path
            )
            or not thumbnail_file_path
            or not os.path.isfile(
                thumbnail_file_path
            )
        ):
            (
                generated_preview,
                generated_thumbnail,
            ) = _generate_preview_if_required(
                image_asset
            )

            preview_file_path = (
                preview_file_path
                or generated_preview
            )

            thumbnail_file_path = (
                thumbnail_file_path
                or generated_thumbnail
            )

    # ------------------------------------------------------------------
    # 3. Register preview artifact
    # ------------------------------------------------------------------

    preview_artifact = None

    if (
        preview_file_path
        and os.path.isfile(
            preview_file_path
        )
    ):
        preview_storage_name = (
            _storage_name_from_path(
                preview_file_path
            )
        )

        # If the generated file is not already in configured storage,
        # register it.
        if (
            not preview_storage_name
            or not default_storage.exists(
                preview_storage_name
            )
        ):
            preview_storage_name = (
                _register_file_in_storage(
                    preview_file_path,
                    (
                        f"previews/"
                        f"{image_asset.id}_rgb.webp"
                    ),
                )
            )

        if preview_storage_name:
            preview_artifact = (
                _create_or_update_artifact(
                    image_asset=image_asset,
                    artifact_type="RGB_PREVIEW",
                    storage_name=preview_storage_name,
                    mime_type="image/webp",
                )
            )

    # ------------------------------------------------------------------
    # 4. Register thumbnail artifact
    # ------------------------------------------------------------------

    thumbnail_artifact = None

    if (
        thumbnail_file_path
        and os.path.isfile(
            thumbnail_file_path
        )
    ):
        thumbnail_storage_name = (
            _storage_name_from_path(
                thumbnail_file_path
            )
        )

        if (
            not thumbnail_storage_name
            or not default_storage.exists(
                thumbnail_storage_name
            )
        ):
            thumbnail_storage_name = (
                _register_file_in_storage(
                    thumbnail_file_path,
                    (
                        f"previews/"
                        f"{image_asset.id}_thumb.webp"
                    ),
                )
            )

        if thumbnail_storage_name:
            thumbnail_artifact = (
                _create_or_update_artifact(
                    image_asset=image_asset,
                    artifact_type="THUMBNAIL",
                    storage_name=thumbnail_storage_name,
                    mime_type="image/webp",
                )
            )

    # ------------------------------------------------------------------
    # 5. Update ImageAsset preview URL
    # ------------------------------------------------------------------

    preview_url = (
        _artifact_url(
            preview_artifact
        )
    )

    if preview_url:
        try:
            if image_asset.preview_url != preview_url:
                image_asset.preview_url = preview_url

                image_asset.save(
                    update_fields=[
                        "preview_url"
                    ]
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 6. Resolve URLs
    # ------------------------------------------------------------------

    geotiff_url = (
        _artifact_url(
            geotiff_artifact
        )
    )

    if not geotiff_url:
        try:
            if image_asset.file:
                geotiff_url = (
                    image_asset.file.url
                )
        except Exception:
            geotiff_url = None

    thumbnail_url = (
        _artifact_url(
            thumbnail_artifact
        )
    )

    # If there is no thumbnail, do NOT substitute another fake/placeholder
    # image. The API simply reports null.
    #
    # ------------------------------------------------------------------
    # 7. Build actual metadata
    # ------------------------------------------------------------------

    acquisition_date = getattr(
        image_asset,
        "acquisition_date",
        None,
    )

    if acquisition_date:
        date_value = str(
            acquisition_date
        )
    else:
        date_value = _get_provenance_value(
            provenance,
            "acquisition_date",
            "date",
            "datetime",
        )

        if date_value is not None:
            date_value = str(
                date_value
            )

    sensor = getattr(
        image_asset,
        "sensor",
        None,
    )

    if not sensor:
        sensor = _get_provenance_value(
            provenance,
            "sensor",
            "satellite",
            "platform",
        )

    product = _get_provenance_value(
        provenance,
        "product",
        "product_type",
        "processing_level",
    )

    source = _get_provenance_value(
        provenance,
        "source",
        "provider",
        "catalog",
    )

    bounds = _serialize_bounds(
        getattr(
            image_asset,
            "bounds_wgs84",
            None,
        )
    )

    cloud_cover = _safe_float(
        getattr(
            image_asset,
            "cloud_cover_pct",
            None,
        )
    )

    resolution = _safe_float(
        getattr(
            image_asset,
            "resolution_m",
            None,
        )
    )

    metadata = _asset_metadata(
        image_asset
    )

    # Add provenance-derived product/source only when actually available.
    if product is not None:
        metadata[
            "product"
        ] = product

    if source is not None:
        metadata[
            "source"
        ] = source

    # ------------------------------------------------------------------
    # 8. Make URLs absolute when request is supplied
    # ------------------------------------------------------------------

    geotiff_url = make_absolute_url(
        geotiff_url,
        request,
    )

    preview_url = make_absolute_url(
        preview_url,
        request,
    )

    thumbnail_url = make_absolute_url(
        thumbnail_url,
        request,
    )

    # ------------------------------------------------------------------
    # 9. Return DTO
    # ------------------------------------------------------------------

    return ImageryArtifactDTO(
        id=str(
            image_asset.id
        ),

        date=date_value,

        satellite=(
            str(sensor)
            if sensor is not None
            else None
        ),

        product=(
            str(product)
            if product is not None
            else None
        ),

        source=(
            str(source)
            if source is not None
            else None
        ),

        geotiff_url=geotiff_url,

        preview_url=preview_url,

        thumbnail_url=thumbnail_url,

        bounds=bounds,

        cloud_cover_pct=cloud_cover,

        resolution_m=resolution,

        preview_path=(
            preview_file_path
            if preview_file_path
            and os.path.isfile(
                preview_file_path
            )
            else None
        ),

        thumbnail_path=(
            thumbnail_file_path
            if thumbnail_file_path
            and os.path.isfile(
                thumbnail_file_path
            )
            else None
        ),

        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------

def get_imagery_artifact_dto(
    image_asset: ImageAsset,
    *,
    request: Optional[Any] = None,
) -> ImageryArtifactDTO:
    """
    Return the currently registered imagery artifacts without forcing
    preview generation.

    Useful for read-only API endpoints.
    """

    return register_imagery_artifacts(
        image_asset,
        request=request,
        generate_preview=False,
    )