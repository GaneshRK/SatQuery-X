"""Root URL Configuration for SatQuery AI per §7."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.imagery.views import (
    DedicatedImageryDetailView,
    DedicatedImageryPreviewView,
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
    SessionContextResetView,
    SessionContextView,
    SessionQueryListCreateView,
)
from apps.reports.views import ReportDetailView, ReportDownloadView, SessionReportListCreateView
from apps.satellite.views import CandidateListView, CandidateSelectView, SatelliteSearchView
from apps.satellite.temporal_views import (
    SatelliteSceneListView,
    SatelliteSceneDetailView,
    AOIListCreateView,
    AOITimelineView,
    ChangeAnalysisView,
    ChangeEventListView,
    SyncStatusView,
    AOIMonitoringView,
)
from apps.system.views import SystemHealthView
from apps.system.demo_views import DemoScenariosListView, BootstrapDemoScenarioView

api_v1_patterns = [
    # Auth
    path("auth/", include("apps.accounts.urls")),

    # System Health & Demo Scenarios
    path("health/", SystemHealthView.as_view(), name="system_health"),
    path("demo-scenarios/", DemoScenariosListView.as_view(), name="demo_scenarios_list"),
    path("demo-scenarios/bootstrap/<str:scenario_key>/", BootstrapDemoScenarioView.as_view(), name="bootstrap_demo_scenario"),

    # Sessions
    path("sessions/", include("apps.sessions.urls")),
    path("sessions/<uuid:session_id>/context/", SessionContextView.as_view(), name="session_context"),
    path("sessions/<uuid:session_id>/context/reset/", SessionContextResetView.as_view(), name="session_context_reset"),

    # Imagery & Pairs under Session
    path("sessions/<uuid:session_id>/images/", SessionImageListCreateView.as_view(), name="session_images"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/", ImageAssetDetailView.as_view(), name="image_detail"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/preview/", ImageAssetPreviewView.as_view(), name="image_preview"),
    path("sessions/<uuid:session_id>/images/<uuid:image_id>/clip_aoi/", ImageAssetClipAOIView.as_view(), name="image_clip_aoi"),
    path("sessions/<uuid:session_id>/pairs/", SessionPairListCreateView.as_view(), name="session_pairs"),
    path("sessions/<uuid:session_id>/pairs/<uuid:pair_id>/", ImagePairDetailView.as_view(), name="pair_detail"),

    # Dynamic XYZ Raster Tiles & Dedicated Imagery Details
    path("imagery/<uuid:image_id>/", DedicatedImageryDetailView.as_view(), name="dedicated_image_detail"),
    path("imagery/<uuid:image_id>/preview/", DedicatedImageryPreviewView.as_view(), name="dedicated_image_preview"),
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

    # Satellite Copernicus & Temporal Observation Engine
    path("satellite/search/", SatelliteSearchView.as_view(), name="satellite_search"),
    path("satellite/search/<uuid:request_id>/candidates/", CandidateListView.as_view(), name="candidate_list"),
    path("satellite/search/<uuid:request_id>/select/", CandidateSelectView.as_view(), name="candidate_select"),
    path("satellite/scenes/", SatelliteSceneListView.as_view(), name="satellite_scenes"),
    path("satellite/scenes/<uuid:scene_id>/", SatelliteSceneDetailView.as_view(), name="satellite_scene_detail"),
    path("satellite/aoi/", AOIListCreateView.as_view(), name="satellite_aoi_list_create"),
    path("satellite/aoi/<uuid:aoi_id>/timeline/", AOITimelineView.as_view(), name="satellite_aoi_timeline"),
    path("satellite/change-analysis/", ChangeAnalysisView.as_view(), name="satellite_change_analysis"),
    path("satellite/change-events/", ChangeEventListView.as_view(), name="satellite_change_events"),
    path("satellite/sync-status/", SyncStatusView.as_view(), name="satellite_sync_status"),
    path("satellite/monitoring/", AOIMonitoringView.as_view(), name="satellite_monitoring"),

    # Model Registry
    path("models/", ModelRegistryListView.as_view(), name="models_list"),
    path("models/<str:model_id>/", ModelRegistryDetailView.as_view(), name="model_detail"),
]

from apps.system.frontend_contract_views import (
    ContractRegisterView,
    ContractLoginView,
    ContractMeView,
    ContractForgotPasswordView,
    ContractVerifyEmailView,
    ContractAnalysisQueryView,
    ContractAnalysisHistoryView,
    ContractAnalysisDetailView,
    ContractProjectListCreateView,
)
from rest_framework_simplejwt.views import TokenRefreshView

frontend_starter_patterns = [
    path("auth/register/", ContractRegisterView.as_view(), name="contract_register"),
    path("auth/login/", ContractLoginView.as_view(), name="contract_login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="contract_token_refresh"),
    path("auth/me/", ContractMeView.as_view(), name="contract_me"),
    path("auth/forgot-password/", ContractForgotPasswordView.as_view(), name="contract_forgot_password"),
    path("auth/verify-email/", ContractVerifyEmailView.as_view(), name="contract_verify_email"),
    path("analysis/query/", ContractAnalysisQueryView.as_view(), name="contract_analysis_query"),
    path("analysis/history/", ContractAnalysisHistoryView.as_view(), name="contract_analysis_history"),
    path("analysis/<str:pk>/", ContractAnalysisDetailView.as_view(), name="contract_analysis_detail"),
    path("imagery/<uuid:image_id>/", DedicatedImageryDetailView.as_view(), name="contract_image_detail"),
    path("imagery/<uuid:image_id>/preview/", DedicatedImageryPreviewView.as_view(), name="contract_image_preview"),
    path("projects/", ContractProjectListCreateView.as_view(), name="contract_projects"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
    path("api/", include(frontend_starter_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
