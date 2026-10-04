"""
API Views and Frontend Views for Fuel Optimization.
Supports POST (JSON) and GET (query params) for easy Postman / browser testing.
"""

import logging
import time
from typing import Dict, Any
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteOptimizeRequestSerializer
from .services.fuel_station_service import FuelStationService
from .services.geocoding_service import geocode_location
from .services.map_service import generate_geojson, generate_route_map
from .services.optimizer_service import plan_fuel_stops
from .services.routing_service import get_route

logger = logging.getLogger(__name__)


def compute_route_optimization(params: Dict[str, Any], request=None) -> tuple:
    """
    Core business logic pipeline:
    1. Geocode Start & Finish (0-2 external calls, 0 if cached/offline dict)
    2. Route via OSRM (1 external call)
    3. Spatial station search (< 20ms)
    4. Plan optimal fuel stops (< 5ms)
    5. Generate GeoJSON & Map

    Returns:
        (api_response: dict, internal_context: dict)
        api_response is the JSON-serializable result sent to clients.
        internal_context contains route_coords, start_info, finish_info for map rendering.
    """
    t0 = time.time()

    # 1. Resolve Start
    if "start_lat" in params and "start_lon" in params:
        start_lat = float(params["start_lat"])
        start_lon = float(params["start_lon"])
        start_name = f"Coordinates ({start_lat:.4f}, {start_lon:.4f})"
    else:
        start_lat, start_lon, start_name = geocode_location(params["start"])

    # 2. Resolve Finish
    if "finish_lat" in params and "finish_lon" in params:
        finish_lat = float(params["finish_lat"])
        finish_lon = float(params["finish_lon"])
        finish_name = f"Coordinates ({finish_lat:.4f}, {finish_lon:.4f})"
    else:
        finish_lat, finish_lon, finish_name = geocode_location(params["finish"])

    # 3. Get Driving Route (1 single call to free OSRM API)
    route_data = get_route(start_lat, start_lon, finish_lat, finish_lon)
    route_coords = route_data["coordinates"]
    total_distance_miles = route_data["distance_miles"]
    cum_dist = route_data["cum_dist"]

    # 4. Find candidate fuel stations along the corridor
    corridor_radius = float(params.get("corridor_radius_miles", 5.0))
    station_service = FuelStationService.get_instance()
    candidate_stations = station_service.find_candidate_stations(
        route_coords=route_coords,
        cum_dist=cum_dist,
        corridor_radius_miles=corridor_radius,
    )

    # 5. Optimize fuel stops
    tank_range = float(params.get("tank_range_miles", 500.0))
    mpg = float(params.get("mpg", 10.0))
    strategy = params.get("strategy", "balanced")

    plan = plan_fuel_stops(
        total_distance_miles=total_distance_miles,
        candidate_stations=candidate_stations,
        tank_range_miles=tank_range,
        mpg=mpg,
        strategy=strategy,
    )

    fuel_stops = plan["stops"]
    summary = plan["summary"]

    start_info = {"lat": start_lat, "lon": start_lon, "display_name": start_name}
    finish_info = {"lat": finish_lat, "lon": finish_lon, "display_name": finish_name}

    # 6. Generate GeoJSON
    geojson_data = generate_geojson(
        route_coords=route_coords,
        start_info=start_info,
        finish_info=finish_info,
        fuel_stops=fuel_stops,
        summary=summary,
    )

    # Build Map View URL
    base_host = request.build_absolute_uri("/")[:-1] if request else "http://127.0.0.1:8000"
    map_view_url = (
        f"{base_host}/api/map-view/?start={start_name}&finish={finish_name}"
        f"&start_lat={start_lat}&start_lon={start_lon}&finish_lat={finish_lat}&finish_lon={finish_lon}"
        f"&tank_range_miles={tank_range}&mpg={mpg}&strategy={strategy}"
    )

    t_elapsed = round((time.time() - t0) * 1000.0, 1)

    api_response = {
        "status": "success",
        "execution_time_ms": t_elapsed,
        "route": {
            "start": start_name,
            "finish": finish_name,
            "start_coordinates": {"lat": start_lat, "lon": start_lon},
            "finish_coordinates": {"lat": finish_lat, "lon": finish_lon},
            "total_distance_miles": total_distance_miles,
            "duration_formatted": route_data["duration_formatted"],
            "duration_seconds": route_data["duration_seconds"],
        },
        "summary": {
            "total_distance_miles": summary["total_distance_miles"],
            "total_fuel_consumed_gallons": summary["total_gallons"],
            "total_fuel_cost_usd": summary["total_cost"],
            "number_of_fuel_stops": summary["number_of_stops"],
            "vehicle_range_miles": summary["tank_range_miles"],
            "vehicle_mpg": summary["mpg"],
            "average_fuel_price_usd": summary["average_price_per_gallon"],
            "cost_per_mile_usd": summary["cost_per_mile"],
            "optimization_strategy": summary["strategy_used"],
        },
        "fuel_stops": fuel_stops,
        "map": {
            "interactive_map_url": map_view_url,
            "geojson": geojson_data,
        },
    }

    internal_context = {
        "route_coords": route_coords,
        "start_info": start_info,
        "finish_info": finish_info,
    }

    return api_response, internal_context


class RouteOptimizeAPIView(APIView):
    """
    Main API Endpoint for Route and Fuel Optimization.
    Accepts:
      - POST (JSON Payload):
        {
          "start": "Los Angeles, CA",
          "finish": "New York, NY",
          "tank_range_miles": 500,
          "mpg": 10,
          "strategy": "balanced"
        }
      - GET (Query Parameters):
        ?start=Los Angeles, CA&finish=New York, NY&tank_range_miles=500&mpg=10
    """

    def get(self, request):
        serializer = RouteOptimizeRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result, _ = compute_route_optimization(serializer.validated_data, request=request)
            response = Response(result, status=status.HTTP_200_OK)
            response["X-Process-Time-Ms"] = str(result["execution_time_ms"])
            return response
        except ValueError as ve:
            return Response({"status": "error", "message": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Error in RouteOptimizeAPIView GET")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = RouteOptimizeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result, _ = compute_route_optimization(serializer.validated_data, request=request)
            response = Response(result, status=status.HTTP_200_OK)
            response["X-Process-Time-Ms"] = str(result["execution_time_ms"])
            return response
        except ValueError as ve:
            return Response({"status": "error", "message": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Error in RouteOptimizeAPIView POST")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InteractiveMapView(APIView):
    """
    Renders the full interactive Folium Leaflet map directly in the browser.
    """

    def get(self, request):
        serializer = RouteOptimizeRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result, internal = compute_route_optimization(serializer.validated_data, request=request)
            html_map = generate_route_map(
                route_coords=internal.get("route_coords", []),
                start_info=internal.get("start_info", {}),
                finish_info=internal.get("finish_info", {}),
                fuel_stops=result.get("fuel_stops", []),
                summary=result.get("summary", {}),
            )
            return HttpResponse(html_map, content_type="text/html")
        except Exception as e:
            return HttpResponse(f"<h3>Error generating map:</h3><p>{e}</p>", status=500, content_type="text/html")


class HealthCheckView(APIView):
    """
    Health check endpoint returning system status and station count.
    """

    def get(self, request):
        service = FuelStationService.get_instance()
        station_count = len(service.df) if service.df is not None else 0
        return Response({
            "status": "healthy",
            "service": "Fuel Route Optimizer API",
            "stations_indexed": station_count,
            "default_tank_range_miles": 500.0,
            "default_mpg": 10.0,
        })


def dashboard_view(request):
    """Renders the modern frontend dashboard."""
    return render(request, "dashboard.html")
