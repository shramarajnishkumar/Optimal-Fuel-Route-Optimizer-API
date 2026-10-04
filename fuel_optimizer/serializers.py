"""
Serializers for Route Optimization API.
"""

from rest_framework import serializers


class RouteOptimizeRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=False,
        allow_blank=False,
        help_text="Start location name or address (e.g. 'Los Angeles, CA' or 'Austin, TX')"
    )
    start_lat = serializers.FloatField(required=False, help_text="Start latitude (e.g. 34.0522)")
    start_lon = serializers.FloatField(required=False, help_text="Start longitude (e.g. -118.2437)")

    finish = serializers.CharField(
        required=False,
        allow_blank=False,
        help_text="Destination location name or address (e.g. 'New York, NY' or 'Seattle, WA')"
    )
    finish_lat = serializers.FloatField(required=False, help_text="Finish latitude (e.g. 40.7128)")
    finish_lon = serializers.FloatField(required=False, help_text="Finish longitude (e.g. -74.0060)")

    tank_range_miles = serializers.FloatField(
        default=500.0,
        min_value=50.0,
        max_value=2000.0,
        help_text="Maximum vehicle range on a single tank in miles (Default: 500.0)"
    )
    mpg = serializers.FloatField(
        default=10.0,
        min_value=1.0,
        max_value=100.0,
        help_text="Vehicle fuel efficiency in miles per gallon (Default: 10.0)"
    )
    corridor_radius_miles = serializers.FloatField(
        default=5.0,
        min_value=0.5,
        max_value=50.0,
        help_text="Highway corridor search radius for fuel stations in miles (Default: 5.0)"
    )
    strategy = serializers.ChoiceField(
        choices=["balanced", "cost_optimal"],
        default="balanced",
        help_text="Fuel stop optimization strategy: 'balanced' (realistic 250-480 mi legs) or 'cost_optimal' (pure DP minimum cost)"
    )

    def validate(self, data):
        # Validate Start
        has_start_text = bool(data.get("start"))
        has_start_coords = "start_lat" in data and "start_lon" in data
        if not has_start_text and not has_start_coords:
            raise serializers.ValidationError(
                {"start": "Must provide either 'start' location name or both 'start_lat' and 'start_lon'."}
            )

        # Validate Finish
        has_finish_text = bool(data.get("finish"))
        has_finish_coords = "finish_lat" in data and "finish_lon" in data
        if not has_finish_text and not has_finish_coords:
            raise serializers.ValidationError(
                {"finish": "Must provide either 'finish' location name or both 'finish_lat' and 'finish_lon'."}
            )

        return data


class FuelStopSerializer(serializers.Serializer):
    stop_number = serializers.IntegerField()
    station_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price_per_gallon = serializers.FloatField()
    coordinates = serializers.DictField()
    mile_marker = serializers.FloatField()
    distance_from_last_stop_miles = serializers.FloatField()
    gallons_refueled = serializers.FloatField()
    cost_at_stop = serializers.FloatField()
    fuel_level_on_arrival_percent = serializers.FloatField(required=False)
