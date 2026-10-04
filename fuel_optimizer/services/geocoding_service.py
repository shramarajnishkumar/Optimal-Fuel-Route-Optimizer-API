"""
Geocoding service to resolve US locations into coordinates (lat, lon).
Uses offline top US cities dictionary for instant zero-latency resolution,
with fallback to Photon / OpenStreetMap Nominatim APIs and in-memory caching.
"""

import logging
import re
import requests
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# USA Geographic bounding box (Continental US + AK/HI)
US_LAT_MIN, US_LAT_MAX = 18.0, 72.0
US_LON_MIN, US_LON_MAX = -180.0, -65.0

# Runtime memory cache (stores dynamically resolved queries during server uptime)
_GEOCODE_CACHE: Dict[str, Tuple[float, float, str]] = {}

# ─────────────────────────────────────────────────────────────
# Top 100+ US cities: instant offline geocoding (0 network calls)
# Key: normalized "city, st" → (lat, lon, display_name)
# ─────────────────────────────────────────────────────────────
TOP_US_CITIES: Dict[str, Tuple[float, float, str]] = {
    # Major metros & state capitals
    "new york, ny": (40.7128, -74.0060, "New York, NY, USA"),
    "los angeles, ca": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "chicago, il": (41.8781, -87.6298, "Chicago, IL, USA"),
    "houston, tx": (29.7604, -95.3698, "Houston, TX, USA"),
    "phoenix, az": (33.4484, -112.0740, "Phoenix, AZ, USA"),
    "philadelphia, pa": (39.9526, -75.1652, "Philadelphia, PA, USA"),
    "san antonio, tx": (29.4241, -98.4936, "San Antonio, TX, USA"),
    "san diego, ca": (32.7157, -117.1611, "San Diego, CA, USA"),
    "dallas, tx": (32.7767, -96.7970, "Dallas, TX, USA"),
    "san jose, ca": (37.3382, -121.8863, "San Jose, CA, USA"),
    "austin, tx": (30.2672, -97.7431, "Austin, TX, USA"),
    "jacksonville, fl": (30.3322, -81.6557, "Jacksonville, FL, USA"),
    "fort worth, tx": (32.7555, -97.3308, "Fort Worth, TX, USA"),
    "columbus, oh": (39.9612, -82.9988, "Columbus, OH, USA"),
    "charlotte, nc": (35.2271, -80.8431, "Charlotte, NC, USA"),
    "san francisco, ca": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "indianapolis, in": (39.7684, -86.1581, "Indianapolis, IN, USA"),
    "seattle, wa": (47.6062, -122.3321, "Seattle, WA, USA"),
    "denver, co": (39.7392, -104.9903, "Denver, CO, USA"),
    "washington, dc": (38.9072, -77.0369, "Washington, DC, USA"),
    "nashville, tn": (36.1627, -86.7816, "Nashville, TN, USA"),
    "oklahoma city, ok": (35.4676, -97.5164, "Oklahoma City, OK, USA"),
    "el paso, tx": (31.7619, -106.4850, "El Paso, TX, USA"),
    "boston, ma": (42.3601, -71.0589, "Boston, MA, USA"),
    "portland, or": (45.5152, -122.6784, "Portland, OR, USA"),
    "las vegas, nv": (36.1699, -115.1398, "Las Vegas, NV, USA"),
    "memphis, tn": (35.1495, -90.0490, "Memphis, TN, USA"),
    "louisville, ky": (38.2527, -85.7585, "Louisville, KY, USA"),
    "baltimore, md": (39.2904, -76.6122, "Baltimore, MD, USA"),
    "milwaukee, wi": (43.0389, -87.9065, "Milwaukee, WI, USA"),
    "albuquerque, nm": (35.0844, -106.6504, "Albuquerque, NM, USA"),
    "tucson, az": (32.2226, -110.9747, "Tucson, AZ, USA"),
    "fresno, ca": (36.7378, -119.7871, "Fresno, CA, USA"),
    "mesa, az": (33.4152, -111.8315, "Mesa, AZ, USA"),
    "sacramento, ca": (38.5816, -121.4944, "Sacramento, CA, USA"),
    "atlanta, ga": (33.7490, -84.3880, "Atlanta, GA, USA"),
    "kansas city, mo": (39.0997, -94.5786, "Kansas City, MO, USA"),
    "colorado springs, co": (38.8339, -104.8214, "Colorado Springs, CO, USA"),
    "omaha, ne": (41.2565, -95.9345, "Omaha, NE, USA"),
    "raleigh, nc": (35.7796, -78.6382, "Raleigh, NC, USA"),
    "miami, fl": (25.7617, -80.1918, "Miami, FL, USA"),
    "cleveland, oh": (41.4993, -81.6944, "Cleveland, OH, USA"),
    "tulsa, ok": (36.1540, -95.9928, "Tulsa, OK, USA"),
    "tampa, fl": (27.9506, -82.4572, "Tampa, FL, USA"),
    "orlando, fl": (28.5383, -81.3792, "Orlando, FL, USA"),
    "new orleans, la": (29.9511, -90.0715, "New Orleans, LA, USA"),
    "minneapolis, mn": (44.9778, -93.2650, "Minneapolis, MN, USA"),
    "saint paul, mn": (44.9537, -93.0900, "Saint Paul, MN, USA"),
    "st. paul, mn": (44.9537, -93.0900, "Saint Paul, MN, USA"),
    "st paul, mn": (44.9537, -93.0900, "Saint Paul, MN, USA"),
    "pittsburgh, pa": (40.4406, -79.9959, "Pittsburgh, PA, USA"),
    "cincinnati, oh": (39.1031, -84.5120, "Cincinnati, OH, USA"),
    "st. louis, mo": (38.6270, -90.1994, "St. Louis, MO, USA"),
    "st louis, mo": (38.6270, -90.1994, "St. Louis, MO, USA"),
    "detroit, mi": (42.3314, -83.0458, "Detroit, MI, USA"),
    "salt lake city, ut": (40.7608, -111.8910, "Salt Lake City, UT, USA"),
    "buffalo, ny": (42.8864, -78.8784, "Buffalo, NY, USA"),
    "honolulu, hi": (21.3069, -157.8583, "Honolulu, HI, USA"),
    "anchorage, ak": (61.2181, -149.9003, "Anchorage, AK, USA"),
    "boise, id": (43.6150, -116.2023, "Boise, ID, USA"),
    "richmond, va": (37.5407, -77.4360, "Richmond, VA, USA"),
    "des moines, ia": (41.5868, -93.6250, "Des Moines, IA, USA"),
    "birmingham, al": (33.5207, -86.8025, "Birmingham, AL, USA"),
    "little rock, ar": (34.7465, -92.2896, "Little Rock, AR, USA"),
    "madison, wi": (43.0731, -89.4012, "Madison, WI, USA"),
    "jackson, ms": (32.2988, -90.1848, "Jackson, MS, USA"),
    "hartford, ct": (41.7658, -72.6734, "Hartford, CT, USA"),
    "charleston, sc": (32.7765, -79.9311, "Charleston, SC, USA"),
    "columbia, sc": (34.0007, -81.0348, "Columbia, SC, USA"),
    "savannah, ga": (32.0809, -81.0912, "Savannah, GA, USA"),
    "knoxville, tn": (35.9606, -83.9207, "Knoxville, TN, USA"),
    "norfolk, va": (36.8508, -76.2859, "Norfolk, VA, USA"),
    "virginia beach, va": (36.8529, -75.9780, "Virginia Beach, VA, USA"),
    "reno, nv": (39.5296, -119.8138, "Reno, NV, USA"),
    "spokane, wa": (47.6588, -117.4260, "Spokane, WA, USA"),
    "tacoma, wa": (47.2529, -122.4443, "Tacoma, WA, USA"),
    "lubbock, tx": (33.5779, -101.8552, "Lubbock, TX, USA"),
    "amarillo, tx": (35.2220, -101.8313, "Amarillo, TX, USA"),
    "wichita, ks": (37.6872, -97.3301, "Wichita, KS, USA"),
    "bakersfield, ca": (35.3733, -119.0187, "Bakersfield, CA, USA"),
    "aurora, co": (39.7294, -104.8319, "Aurora, CO, USA"),
    "rochester, ny": (43.1566, -77.6088, "Rochester, NY, USA"),
    "baton rouge, la": (30.4515, -91.1871, "Baton Rouge, LA, USA"),
    "riverside, ca": (33.9533, -117.3962, "Riverside, CA, USA"),
    "stockton, ca": (37.9577, -121.2908, "Stockton, CA, USA"),
    "newark, nj": (40.7357, -74.1724, "Newark, NJ, USA"),
    "jersey city, nj": (40.7178, -74.0431, "Jersey City, NJ, USA"),
    "lexington, ky": (38.0406, -84.5037, "Lexington, KY, USA"),
    "greensboro, nc": (36.0726, -79.7920, "Greensboro, NC, USA"),
    "lincoln, ne": (40.8136, -96.7026, "Lincoln, NE, USA"),
    "scottsdale, az": (33.4942, -111.9261, "Scottsdale, AZ, USA"),
    "plano, tx": (33.0198, -96.6989, "Plano, TX, USA"),
    "laredo, tx": (27.5036, -99.5076, "Laredo, TX, USA"),
    "durham, nc": (35.9940, -78.8986, "Durham, NC, USA"),
    "cheyenne, wy": (41.1400, -104.8202, "Cheyenne, WY, USA"),
    "helena, mt": (46.5884, -112.0245, "Helena, MT, USA"),
    "billings, mt": (45.7833, -108.5007, "Billings, MT, USA"),
    "sioux falls, sd": (43.5446, -96.7311, "Sioux Falls, SD, USA"),
    "fargo, nd": (46.8772, -96.7898, "Fargo, ND, USA"),
    "santa fe, nm": (35.6870, -105.9378, "Santa Fe, NM, USA"),
    "tallahassee, fl": (30.4383, -84.2807, "Tallahassee, FL, USA"),
    "charleston, wv": (38.3498, -81.6326, "Charleston, WV, USA"),
    "providence, ri": (41.8240, -71.4128, "Providence, RI, USA"),
    "wilmington, de": (39.7391, -75.5398, "Wilmington, DE, USA"),
    "burlington, vt": (44.4759, -73.2121, "Burlington, VT, USA"),
    "portland, me": (43.6591, -70.2568, "Portland, ME, USA"),
    "concord, nh": (43.2081, -71.5376, "Concord, NH, USA"),
    "trenton, nj": (40.2206, -74.7699, "Trenton, NJ, USA"),
    "albany, ny": (42.6526, -73.7562, "Albany, NY, USA"),
    "harrisburg, pa": (40.2732, -76.8867, "Harrisburg, PA, USA"),
    "dover, de": (39.1582, -75.5244, "Dover, DE, USA"),
    "annapolis, md": (38.9784, -76.4922, "Annapolis, MD, USA"),
    "montgomery, al": (32.3792, -86.3077, "Montgomery, AL, USA"),
    "topeka, ks": (39.0489, -95.6780, "Topeka, KS, USA"),
    "olympia, wa": (47.0379, -122.9007, "Olympia, WA, USA"),
    "salem, or": (44.9429, -123.0351, "Salem, OR, USA"),
    "juneau, ak": (58.3005, -134.4197, "Juneau, AK, USA"),
    "lansing, mi": (42.7325, -84.5555, "Lansing, MI, USA"),
    "frankfort, ky": (38.2009, -84.8733, "Frankfort, KY, USA"),
    "jefferson city, mo": (38.5767, -92.1735, "Jefferson City, MO, USA"),
    "pierre, sd": (44.3683, -100.3510, "Pierre, SD, USA"),
    "bismarck, nd": (46.8083, -100.7837, "Bismarck, ND, USA"),
    "carson city, nv": (39.1638, -119.7674, "Carson City, NV, USA"),
    "montpelier, vt": (44.2601, -72.5754, "Montpelier, VT, USA"),
    "augusta, me": (44.3106, -69.7795, "Augusta, ME, USA"),
    "springfield, il": (39.7817, -89.6501, "Springfield, IL, USA"),
}


def normalize_query(query: str) -> str:
    """Normalize input query string for caching and API query."""
    s = query.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[,\s]+usa?$", "", s)  # strip trailing USA / US
    return s.strip()


def is_within_usa(lat: float, lon: float) -> bool:
    """Check if coordinates fall within USA boundaries."""
    return US_LAT_MIN <= lat <= US_LAT_MAX and US_LON_MIN <= lon <= US_LON_MAX


def geocode_location(location_input: Any) -> Tuple[float, float, str]:
    """
    Dynamically geocodes any US location input into (latitude, longitude, display_name).
    Accepts:
      - string address/city (e.g. 'Los Angeles, CA', 'Austin, TX', '1600 Pennsylvania Ave, Washington, DC')
      - tuple or list [lat, lon]
      - dict with 'lat' and 'lon'/'lng'
    Raises:
      - ValueError if location cannot be found or is outside USA.
    """
    # 1. Direct coordinate tuple/list
    if isinstance(location_input, (list, tuple)) and len(location_input) == 2:
        lat, lon = float(location_input[0]), float(location_input[1])
        if not is_within_usa(lat, lon):
            raise ValueError(f"Coordinates ({lat}, {lon}) are outside the United States.")
        return lat, lon, f"Coordinates ({lat:.4f}, {lon:.4f})"

    # 2. Coordinate dict
    if isinstance(location_input, dict):
        lat = location_input.get("lat") or location_input.get("latitude")
        lon = location_input.get("lon") or location_input.get("lng") or location_input.get("longitude")
        if lat is not None and lon is not None:
            lat, lon = float(lat), float(lon)
            if not is_within_usa(lat, lon):
                raise ValueError(f"Coordinates ({lat}, {lon}) are outside the United States.")
            return lat, lon, f"Coordinates ({lat:.4f}, {lon:.4f})"

    if not isinstance(location_input, str) or not location_input.strip():
        raise ValueError("Invalid location input. Please provide a valid US city, address, or coordinates.")

    query = location_input.strip()
    norm_q = normalize_query(query)

    # 3. Check runtime cache (previously fetched dynamic results)
    if norm_q in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[norm_q]

    # 4. Instant offline lookup: Top 100+ US cities (0 network calls)
    if norm_q in TOP_US_CITIES:
        result = TOP_US_CITIES[norm_q]
        _GEOCODE_CACHE[norm_q] = result
        logger.debug(f"Geocoded '{query}' from offline dictionary (0 API calls).")
        return result

    # 5. Dynamic Geocoding via Photon API (Fast OpenStreetMap-based geocoder, free, no key)
    try:
        url = "https://photon.komoot.io/api/"
        params = {"q": f"{query}, United States", "limit": 1}
        resp = requests.get(url, params=params, timeout=6, headers={"User-Agent": "FuelOptimizer/1.0"})
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            if features:
                feat = features[0]
                lon, lat = feat["geometry"]["coordinates"]
                props = feat.get("properties", {})
                country = props.get("country", "")
                country_code = props.get("countrycode", "")
                
                # Check country and bounds
                if country_code.upper() in ["US", "USA"] or country in ["United States", "USA", "United States of America"] or is_within_usa(lat, lon):
                    name_parts = [props.get("name"), props.get("city"), props.get("state"), "USA"]
                    display_name = ", ".join([p for p in name_parts if p]) or query
                    result = (lat, lon, display_name)
                    _GEOCODE_CACHE[norm_q] = result
                    return result
    except Exception as e:
        logger.warning(f"Photon dynamic geocoding error for '{query}': {e}")

    # 6. Fallback: OpenStreetMap Nominatim
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": query, "format": "json", "countrycodes": "us", "limit": 1}
        headers = {"User-Agent": "FuelOptimizerAssessment/1.0 (contact: assessment@example.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                item = data[0]
                lat = float(item["lat"])
                lon = float(item["lon"])
                if is_within_usa(lat, lon):
                    result = (lat, lon, item.get("display_name", query))
                    _GEOCODE_CACHE[norm_q] = result
                    return result
    except Exception as e:
        logger.warning(f"Nominatim geocoding error for '{query}': {e}")

    raise ValueError(f"Could not resolve '{query}' to a valid location within the USA. Please check spelling or provide state abbreviation (e.g. 'Austin, TX').")
