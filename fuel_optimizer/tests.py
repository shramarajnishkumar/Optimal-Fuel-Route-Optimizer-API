"""
Comprehensive Test Suite for Fuel Optimizer Application.
Includes unit tests for services and integration tests for Django REST API endpoints.
"""

from django.test import TestCase, Client
from rest_framework import status
from .services.geocoding_service import geocode_location, is_within_usa, normalize_query, TOP_US_CITIES
from .services.routing_service import haversine_miles, format_duration
from .services.fuel_station_service import FuelStationService
from .services.optimizer_service import plan_fuel_stops


class GeocodingServiceTests(TestCase):
    def test_major_city_lookup(self):
        lat, lon, name = geocode_location("Los Angeles, CA")
        self.assertAlmostEqual(lat, 34.0522, places=2)
        self.assertAlmostEqual(lon, -118.2437, places=2)
        self.assertTrue(is_within_usa(lat, lon))

    def test_direct_coordinate_input(self):
        lat, lon, name = geocode_location([40.7128, -74.0060])
        self.assertAlmostEqual(lat, 40.7128, places=4)
        self.assertAlmostEqual(lon, -74.0060, places=4)

    def test_outside_usa_coordinates(self):
        with self.assertRaises(ValueError):
            geocode_location([51.5074, -0.1278])  # London, UK

    def test_offline_dictionary_hits(self):
        """Verifies that top US cities resolve from the offline dictionary without API calls."""
        for city_key in ["new york, ny", "chicago, il", "miami, fl", "seattle, wa", "dallas, tx"]:
            self.assertIn(city_key, TOP_US_CITIES)
            lat, lon, name = geocode_location(city_key.title())
            self.assertTrue(is_within_usa(lat, lon))
            self.assertIn("USA", name)


class RoutingServiceTests(TestCase):
    def test_haversine_distance(self):
        # Distance between LA and NYC is ~2,445 air miles
        d = haversine_miles(34.0522, -118.2437, 40.7128, -74.0060)
        self.assertTrue(2400 < d < 2500)

    def test_format_duration(self):
        self.assertEqual(format_duration(3600), "1 hr")
        self.assertEqual(format_duration(90000), "1 day, 1 hr")

    def test_format_duration_edge_cases(self):
        self.assertEqual(format_duration(0), "0 mins")
        self.assertIn("min", format_duration(60))


class FuelStationServiceTests(TestCase):
    def test_stations_loaded_and_indexed(self):
        service = FuelStationService.get_instance()
        self.assertIsNotNone(service.df)
        self.assertGreater(len(service.df), 5000)
        self.assertIsNotNone(service.kdtree)


class OptimizerServiceTests(TestCase):
    def test_trip_under_500_miles(self):
        result = plan_fuel_stops(
            total_distance_miles=350.0,
            candidate_stations=[],
            tank_range_miles=500.0,
            mpg=10.0,
        )
        self.assertEqual(result["summary"]["number_of_stops"], 0)
        self.assertEqual(result["summary"]["total_gallons"], 35.0)

    def test_multi_stop_planning(self):
        # Create mock candidate stations along a 1,200 mile route
        mock_stations = [
            {"station_id": 1, "name": "Stop 1", "address": "A1", "city": "C1", "state": "TX", "price": 3.00, "lat": 32.0, "lng": -97.0, "mile_marker": 400.0, "dist_to_route": 1.0},
            {"station_id": 2, "name": "Stop 2", "address": "A2", "city": "C2", "state": "MO", "price": 2.80, "lat": 38.0, "lng": -92.0, "mile_marker": 800.0, "dist_to_route": 1.0},
        ]
        result = plan_fuel_stops(
            total_distance_miles=1200.0,
            candidate_stations=mock_stations,
            tank_range_miles=500.0,
            mpg=10.0,
            strategy="balanced",
        )
        self.assertEqual(result["summary"]["total_gallons"], 120.0)
        self.assertGreaterEqual(result["summary"]["number_of_stops"], 2)

    def test_cost_optimal_strategy(self):
        """Verifies the DP cost-optimal strategy finds a valid path and minimizes cost."""
        mock_stations = [
            {"station_id": 10, "name": "Cheap A", "address": "X1", "city": "A", "state": "TX", "price": 2.50, "lat": 31.0, "lng": -96.0, "mile_marker": 300.0, "dist_to_route": 1.0},
            {"station_id": 11, "name": "Expensive B", "address": "X2", "city": "B", "state": "OK", "price": 4.00, "lat": 34.0, "lng": -93.0, "mile_marker": 450.0, "dist_to_route": 1.0},
            {"station_id": 12, "name": "Cheap C", "address": "X3", "city": "C", "state": "MO", "price": 2.60, "lat": 37.0, "lng": -90.0, "mile_marker": 750.0, "dist_to_route": 1.0},
        ]
        result = plan_fuel_stops(
            total_distance_miles=1000.0,
            candidate_stations=mock_stations,
            tank_range_miles=500.0,
            mpg=10.0,
            strategy="cost_optimal",
        )
        self.assertEqual(result["summary"]["strategy_used"], "cost_optimal_dynamic_programming")
        self.assertGreater(result["summary"]["total_cost"], 0)
        self.assertEqual(result["summary"]["total_gallons"], 100.0)
        # Cost-optimal should not choose the expensive station when cheaper alternatives exist
        selected_ids = [s["station_id"] for s in result["stops"]]
        self.assertNotIn(11, selected_ids)

    def test_no_stations_raises_error(self):
        """Route longer than 500 miles with no stations should raise ValueError."""
        with self.assertRaises(ValueError):
            plan_fuel_stops(
                total_distance_miles=800.0,
                candidate_stations=[],
                tank_range_miles=500.0,
                mpg=10.0,
            )


class APITests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "healthy")

    def test_route_optimize_post_success(self):
        payload = {
            "start": "Dallas, TX",
            "finish": "Chicago, IL",
            "tank_range_miles": 500,
            "mpg": 10,
        }
        response = self.client.post("/api/route-optimize/", payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("route", data)
        self.assertIn("summary", data)
        self.assertIn("fuel_stops", data)
        self.assertIn("map", data)

    def test_route_optimize_get_with_query_params(self):
        """Verifies that the GET endpoint with query parameters works identically to POST."""
        response = self.client.get("/api/route-optimize/?start=Dallas, TX&finish=Chicago, IL&tank_range_miles=500&mpg=10")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("summary", data)

    def test_route_optimize_validation_error(self):
        # Missing destination
        payload = {"start": "Dallas, TX"}
        response = self.client.post("/api/route-optimize/", payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_interactive_map_view(self):
        response = self.client.get("/api/map-view/?start=Dallas, TX&finish=Chicago, IL")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/html", response["Content-Type"])
