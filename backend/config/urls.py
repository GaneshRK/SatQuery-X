"""Root URL Configuration for SatQuery AI per §7."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.imagery.views import (
    ImageAssetClipAOIView,
    ImageAssetDetailView,
    ImageAssetPreviewView,
    ImageAssetTileView,
    ImagePairDetailView,
    SessionImageListCreateView,
    SessionPairListCreateView,
)
from apps.models_ai.views import ModelRegistryDetailView, ModelRegistryListView
from apps.queries.views import (
    QueryDetailView,
    QueryExportView,
    QueryStreamView,
    SessionQueryListCreateView,
)
from apps.reports.views import ReportDetailView, ReportDownloadView, SessionReportListCreateView
from apps.satellite.views import CandidateListView, CandidateSelectView, SatelliteSearchView
from apps.system.views import SystemHealthView

api_v1_patterns = [
    # Auth
    path("auth/", include("apps.accounts.urls")),

    # System Health
    path("health/", SystemHealthView.as_view(), name="system_health"),

    # Sessions
    path("sessions/", include("apps.sessions.urls")),

    # Imagery & Pairs under Session
    path("sessions/<uuid:session_id>/images/", SessionImageListCreateView.as_view(), name="session_images"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/", ImageAssetDetailView.as_view(), name="image_detail"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/preview/", ImageAssetPreviewView.as_view(), name="image_preview"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/clip_aoi/", ImageAssetClipAOIView.as_view(), name="image_clip_aoi"),
    path("sessions/<uuid:session_id>/pairs/", SessionPairListCreateView.as_view(), name="session_pairs"),
    path("sessions/<uuid:session_id>/pairs/<uuid:pair_id>/", ImagePairDetailView.as_view(), name="pair_detail"),

    # Dynamic XYZ Raster Tiles
    path("imagery/<uuid:image_id>/tiles/<int:z>/<int:x>/<int:y>/", ImageAssetTileView.as_view(), name="image_tiles"),

    # Queries & SSE stream & Multi-Format Exports
    path("sessions/<uuid:session_id>/queries/", SessionQueryListCreateView.as_view(), name="session_queries"),
    path("sessions/<uuid:session_id>/queries/<uuid:query_id>/", QueryDetailView.as_view(), name="query_detail"),
    path("sessions/<uuid:session_id>/queries/<uuid:query_id>/stream/", QueryStreamView.as_view(), name="query_stream"),
    path("sessions/<uuid:session_id>/queries/<uuid:query_id>/export/<str:export_format>/", QueryExportView.as_view(), name="query_export"),

    # Reports
    path("sessions/<uuid:session_id>/reports/", SessionReportListCreateView.as_view(), name="session_reports"),
    path("sessions/<uuid:session_id>/reports/<uuid:report_id>/", ReportDetailView.as_view(), name="report_detail"),
    path("sessions/<uuid:session_id>/reports/<uuid:report_id>/download/", ReportDownloadView.as_view(), name="report_download"),

    # Satellite Copernicus
    path("satellite/search/", SatelliteSearchView.as_view(), name="satellite_search"),
    path("satellite/search/<uuid:request_id>/candidates/", CandidateListView.as_view(), name="candidate_list"),
    path("satellite/search/<uuid:request_id>/select/", CandidateSelectView.as_view(), name="candidate_select"),

    # Model Registry
    path("models/", ModelRegistryListView.as_view(), name="models_list"),
    path("models/<str:model_id>/", ModelRegistryDetailView.as_view(), name="model_detail"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
