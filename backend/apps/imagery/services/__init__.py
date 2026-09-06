"""
Imagery service layer.

This package contains the services responsible for:

- Raster visualization and browser previews
- Change-mask derivative generation
- Imagery artifact registration
- Artifact DTOs
"""

from .preview import (
    generate_change_mask_artifact,
    generate_rgb_preview,
    generate_thumbnail_image,
)

from .artifacts import (
    AnalysisArtifactDTO,
    ImageryArtifactDTO,
    get_imagery_artifact_dto,
    make_absolute_url,
    register_imagery_artifacts,
)


__all__ = [
    # Preview / derivative generation
    "generate_rgb_preview",
    "generate_change_mask_artifact",
    "generate_thumbnail_image",

    # Artifact DTOs
    "ImageryArtifactDTO",
    "AnalysisArtifactDTO",

    # Artifact registry
    "register_imagery_artifacts",
    "get_imagery_artifact_dto",

    # URL helper
    "make_absolute_url",
]