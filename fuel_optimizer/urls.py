"""
URL routing for Fuel Optimizer application.
"""

from django.urls import path
from .views import (
    RouteOptimizeAPIView,
    InteractiveMapView,
    HealthCheckView,
    dashboard_view,
)

urlpatterns = [
    # Interactive Frontend Dashboard
    path("", dashboard_view, name="dashboard"),

    # REST API Endpoints
    path("api/route-optimize/", RouteOptimizeAPIView.as_view(), name="route-optimize"),
    path("api/optimize/", RouteOptimizeAPIView.as_view(), name="route-optimize-alias"),
    path("api/map-view/", InteractiveMapView.as_view(), name="map-view"),
    path("api/health/", HealthCheckView.as_view(), name="health-check"),
]
