"""
Routing service using the free Open Source Routing Machine (OSRM) API.
Performs exactly 1 routing call to fetch full route geometry, distance, and duration.
Includes fallback mirrors, cumulative distance calculation, and error resilience.
"""

import logging
import math
from typing import Dict, Any, List, Tuple
import requests

logger = logging.getLogger(__name__)

# Primary and fallback public OSRM driving endpoints (all 100% free, no API key needed)
OSRM_SERVERS = [
    "http://router.project-osrm.org",
    "https://routing.openstreetmap.de/routed-car",
]

# Simple in-memory cache for routes: key=(round(lat1,4), round(lon1,4), round(lat2,4), round(lon2,4))
_ROUTE_CACHE: Dict[Tuple[float, float, float, float], Dict[str, Any]] = {}


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable string (e.g. '1 day, 3 hrs, 15 mins')."""
    total_minutes = int(round(seconds / 60.0))
    days, rem_minutes = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem_minutes, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hr{'s' if hours > 1 else ''}")
    if minutes > 0 or not parts:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    return ", ".join(parts)


def get_route(
    start_lat: float, start_lon: float,
    finish_lat: float, finish_lon: float
) -> Dict[str, Any]:
    """
    Fetches the driving route between start and finish points using OSRM.
    Returns:
      {
        'coordinates': [[lon, lat], ...],
        'distance_miles': float,
        'duration_seconds': float,
        'duration_formatted': str,
        'cum_dist': [0.0, ... cumulative miles ...]
      }
    """
    cache_key = (round(start_lat, 4), round(start_lon, 4), round(finish_lat, 4), round(finish_lon, 4))
    if cache_key in _ROUTE_CACHE:
        return _ROUTE_CACHE[cache_key]

    last_error = None
    for base_url in OSRM_SERVERS:
        # Note: OSRM expects {lon},{lat} format
        endpoint = f"{base_url}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }
        try:
            resp = requests.get(endpoint, params=params, timeout=15, headers={"User-Agent": "FuelOptimizer/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    route_data = data["routes"][0]
                    coords = route_data["geometry"]["coordinates"]  # list of [lon, lat]
                    distance_meters = route_data.get("distance", 0.0)
                    duration_seconds = route_data.get("duration", 0.0)

                    # Compute cumulative distance along coordinate path
                    cum_dist: List[float] = [0.0]
                    for i in range(1, len(coords)):
                        d = haversine_miles(coords[i - 1][1], coords[i - 1][0], coords[i][1], coords[i][0])
                        cum_dist.append(cum_dist[-1] + d)

                    total_dist_miles = distance_meters * 0.000621371
                    # Ensure cumulative distance aligns closely with OSRM total distance
                    if cum_dist and cum_dist[-1] > 0 and abs(cum_dist[-1] - total_dist_miles) > 1.0:
                        scale = total_dist_miles / cum_dist[-1]
                        cum_dist = [d * scale for d in cum_dist]
                    else:
                        total_dist_miles = cum_dist[-1] if cum_dist else total_dist_miles

                    result = {
                        "coordinates": coords,
                        "distance_miles": round(total_dist_miles, 2),
                        "duration_seconds": round(duration_seconds, 1),
                        "duration_formatted": format_duration(duration_seconds),
                        "cum_dist": cum_dist,
                    }
                    _ROUTE_CACHE[cache_key] = result
                    return result
                else:
                    last_error = f"OSRM returned no route: {data.get('message', 'Unknown error')}"
            else:
                last_error = f"OSRM HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Error querying OSRM at {base_url}: {e}")

    raise RuntimeError(f"Failed to calculate route between points. Error details: {last_error}")
