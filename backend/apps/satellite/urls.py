"""
URL configuration for the SatQuery-X satellite intelligence subsystem.
"""

from django.urls import path

from .acquisition_views import (
    AcquisitionCandidatesForRequestView,
    AcquisitionRetrievedAssetView,
    AcquisitionRequestStatusView,
    AcquireSelectedCandidateView,
    CancelAcquisitionRequestView,
    RetryAcquisitionCandidateView,
    SelectAcquisitionCandidateView,
)
from .views import (
    AreaOfInterestDetailView,
    AreaOfInterestListCreateView,
    ChangeDetectionRequestView,
    ChangeEventDetailView,
    ChangeEventListView,
    HistoricalCatalogueSearchView,
    MonitoringAlertDetailView,
    MonitoringAlertListView,
    MonitoringPlanDetailView,
    MonitoringPlanListCreateView,
    SatelliteCapabilityView,
    SatelliteCatalogueSyncView,
    SatelliteCollectionListView,
    SatelliteSceneDetailView,
    SatelliteSceneEvidenceView,
    SatelliteSceneListView,
    TemporalObservationDetailView,
    TemporalObservationListView,
)


app_name = "satellite"


urlpatterns = [
    # -------------------------------------------------------------------------
    # Areas of Interest
    # -------------------------------------------------------------------------

    path(
        "aois/",
        AreaOfInterestListCreateView.as_view(),
        name="aoi-list-create",
    ),
    path(
        "aois/<uuid:pk>/",
        AreaOfInterestDetailView.as_view(),
        name="aoi-detail",
    ),

    # -------------------------------------------------------------------------
    # Satellite catalogue
    # -------------------------------------------------------------------------

    path(
        "collections/",
        SatelliteCollectionListView.as_view(),
        name="collection-list",
    ),
    path(
        "scenes/",
        SatelliteSceneListView.as_view(),
        name="scene-list",
    ),
    path(
        "scenes/<uuid:pk>/",
        SatelliteSceneDetailView.as_view(),
        name="scene-detail",
    ),
    path(
        "scenes/<uuid:scene_id>/evidence/",
        SatelliteSceneEvidenceView.as_view(),
        name="scene-evidence",
    ),

    # -------------------------------------------------------------------------
    # Historical catalogue search
    # -------------------------------------------------------------------------

    path(
        "catalogue/search/",
        HistoricalCatalogueSearchView.as_view(),
        name="catalogue-search",
    ),

    # -------------------------------------------------------------------------
    # Acquisition requests
    # -------------------------------------------------------------------------

    path(
        "acquisition/requests/",
        AcquisitionRequestStatusView.as_view(),
        name="acquisition-request-status-base",
    ),

    path(
        "acquisition/requests/<uuid:request_id>/",
        AcquisitionRequestStatusView.as_view(),
        name="acquisition-request-status",
    ),

    path(
        "acquisition/requests/<uuid:request_id>/candidates/",
        AcquisitionCandidatesForRequestView.as_view(),
        name="acquisition-request-candidates",
    ),

    path(
        "acquisition/requests/<uuid:request_id>/cancel/",
        CancelAcquisitionRequestView.as_view(),
        name="acquisition-request-cancel",
    ),

    # -------------------------------------------------------------------------
    # Acquisition candidates
    # -------------------------------------------------------------------------

    path(
        "acquisition/candidates/<uuid:candidate_id>/select/",
        SelectAcquisitionCandidateView.as_view(),
        name="acquisition-candidate-select",
    ),

    path(
        "acquisition/candidates/<uuid:candidate_id>/acquire/",
        AcquireSelectedCandidateView.as_view(),
        name="acquisition-candidate-acquire",
    ),

    path(
        "acquisition/candidates/<uuid:candidate_id>/retry/",
        RetryAcquisitionCandidateView.as_view(),
        name="acquisition-candidate-retry",
    ),

    path(
        "acquisition/candidates/<uuid:candidate_id>/",
        AcquisitionRetrievedAssetView.as_view(),
        name="acquisition-candidate-detail",
    ),

    path(
        "acquisition/candidates/<uuid:candidate_id>/asset/",
        AcquisitionRetrievedAssetView.as_view(),
        name="acquisition-candidate-asset",
    ),

    # -------------------------------------------------------------------------
    # Temporal observations
    # -------------------------------------------------------------------------

    path(
        "observations/",
        TemporalObservationListView.as_view(),
        name="observation-list",
    ),
    path(
        "observations/<uuid:pk>/",
        TemporalObservationDetailView.as_view(),
        name="observation-detail",
    ),

    # -------------------------------------------------------------------------
    # Change events
    # -------------------------------------------------------------------------

    path(
        "changes/",
        ChangeEventListView.as_view(),
        name="change-list",
    ),
    path(
        "changes/<uuid:pk>/",
        ChangeEventDetailView.as_view(),
        name="change-detail",
    ),
    path(
        "changes/detect/",
        ChangeDetectionRequestView.as_view(),
        name="change-detect",
    ),

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    path(
        "monitoring/plans/",
        MonitoringPlanListCreateView.as_view(),
        name="monitoring-plan-list-create",
    ),
    path(
        "monitoring/plans/<uuid:pk>/",
        MonitoringPlanDetailView.as_view(),
        name="monitoring-plan-detail",
    ),
    path(
        "monitoring/alerts/",
        MonitoringAlertListView.as_view(),
        name="monitoring-alert-list",
    ),
    path(
        "monitoring/alerts/<uuid:pk>/",
        MonitoringAlertDetailView.as_view(),
        name="monitoring-alert-detail",
    ),

    # -------------------------------------------------------------------------
    # Catalogue synchronization
    # -------------------------------------------------------------------------

    path(
        "catalogue/sync/",
        SatelliteCatalogueSyncView.as_view(),
        name="catalogue-sync",
    ),

    # -------------------------------------------------------------------------
    # Capability / health information
    # -------------------------------------------------------------------------

    path(
        "capabilities/",
        SatelliteCapabilityView.as_view(),
        name="capabilities",
    ),
]