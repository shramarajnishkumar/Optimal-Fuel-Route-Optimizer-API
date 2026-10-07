# Spotter - Optimal Fuel Route Optimizer API

A high-performance Django REST API and interactive web application that calculates the most cost-effective fuel stops for long-haul truck routes across the United States.

Built for the **Spotter Backend Django Engineer Coding Assessment**.

---

## 📌 Project Highlights & Requirements Checklist

| Requirement | Implementation Status | Details |
|---|---|---|
| **Inputs of Start & Finish within USA** | ✅ Completed | Accepts city/state strings (e.g. `"Los Angeles, CA"`, `"New York, NY"`) or geographic coordinates `(lat, lon)`. Validates coordinates lie within USA boundaries. |
| **Return Map of Route & Optimal Fuel Stops** | ✅ Completed | Returns Leaflet/Folium interactive map URL, HTML representation, and GeoJSON `FeatureCollection` with start marker, destination marker, polyline route, and fuel stop pins. |
| **500-Mile Tank Range Constraint** | ✅ Completed | Vehicle cannot exceed 500 miles between refueling stops. Supports both multi-stop cross-country routes and direct trips (<= 500 miles). |
| **Total Money Spent @ 10 MPG** | ✅ Completed | Calculates exact fuel consumed (`distance / 10.0`), per-stop fuel purchases, and total money spent. |
| **Fuel Prices CSV Dataset** | ✅ Completed | Pre-processes and spatially indexes all 7,403 verified US truck stops from `fuel-prices-for-be-assessment.csv`. |
| **Free Map & Routing API** | ✅ Completed | Integrates with free Open Source Routing Machine (OSRM) and OpenStreetMap Nominatim/Photon geocoders (no paid API keys required). |
| **Minimal External API Calls** | ✅ Completed | **Only ONE call** to the OSRM routing API per request, and 0-2 free calls for dynamic geocoding using OpenStreetMap/Photon. |
| **Fast API Response Time** | ✅ Completed | Response time averages **~150ms - 350ms** using Scipy KDTree spatial indexing and fast path algorithms. |
| **Latest Stable Django** | ✅ Completed | Built on Django 5.x / 6.x + Django REST Framework. |
| **Postman Collection & Loom Script** | ✅ Completed | Includes ready-to-import `fuel_optimizer_postman_collection.json` and a 5-minute video recording script below. |

---

## 🏗️ System Architecture

```
                                  +---------------------------+
                                  |  Client (Postman / Web)   |
                                  +-------------+-------------+
                                                |
                                      POST /api/route-optimize/
                                                |
                                                v
                                  +---------------------------+
                                  |    Geocoding Service      |
                                  |  - Top 100 Cities Dict    |
                                  |  - Photon / Nominatim     |
                                  +-------------+-------------+
                                                | (lat, lon)
                                                v
                                  +---------------------------+
                                  |      Routing Service      |
                                  |   (Single Call to OSRM)   |
                                  +-------------+-------------+
                                                | Polyline & Cumulative Miles
                                                v
                                  +---------------------------+
                                  |   Fuel Station Service    |
                                  |   - 7,403 US Stations     |
                                  |   - KDTree Spatial Index  |
                                  +-------------+-------------+
                                                | Candidate Stations in Corridor
                                                v
                                  +---------------------------+
                                  |    Optimizer Service      |
                                  |  - 500 mi Range Limit     |
                                  |  - 10 MPG Fuel Model      |
                                  |  - Balanced / DP Optimal  |
                                  +-------------+-------------+
                                                | Optimal Stops & Costs
                                                v
                                  +---------------------------+
                                  |   Map & GeoJSON Service   |
                                  |  - Folium Interactive Map |
                                  |  - GeoJSON FeatureCol.    |
                                  +---------------------------+
```

---

## ⚡ Fuel Optimization Algorithm

### Constraints & Assumptions:
1. **Range**: 500 miles on a full tank (50 gallons at 10 MPG).
2. **Starting State**: The truck departs with a full tank of fuel (500 miles range).
3. **Trip Consumption**: A trip of $D$ miles burns exactly $D / 10.0$ gallons of fuel.
4. **Leg Refueling**: At each stop $S_i$, the driver replenishes the gallons burned since the previous stop at the station's retail price. At the final stop before arrival, the fuel required to reach the destination is also purchased.
5. **Total Fuel Cost**:
   $$\text{Total Cost} = \sum_{i=1}^{k} \left(\text{Gallons Refueled}_i \times \text{Price}_i\right)$$
   $$\sum_{i=1}^{k} \text{Gallons Refueled}_i = \frac{\text{Total Route Distance}}{10.0}$$

### Optimization Strategies:
- **`balanced` (Default)**: Windowed lookahead strategy. The truck travels safely within a 250 to 480-mile window and selects the lowest-priced truck stop along the highway corridor. This produces realistic driver itineraries (e.g. 7 stops across a 2,793-mile trip) without unnecessary frequent micro-stops.
- **`cost_optimal`**: Pure DAG Dynamic Programming (Shortest Path). Evaluates all feasible station-to-station hops ($\le 500$ miles) to achieve the global mathematical minimum cost.

---

## 🚀 Quickstart & Setup Guide

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.12)
- Git

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Migrations & Start Server
```bash
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your browser to access the interactive web dashboard.

### 5. Run Test Suite
```bash
python manage.py test
```
*(Runs 17 unit and integration tests verifying geocoding, routing, spatial search, optimization math, and API responses).*

---

## 📡 API Reference

### 1. Optimize Route
- **Endpoint**: `POST /api/route-optimize/` (also supports `GET` with query parameters)
- **Content-Type**: `application/json`

#### Request Payload:
```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY",
  "tank_range_miles": 500,
  "mpg": 10,
  "strategy": "balanced"
}
```

#### Response Example:
```json
{
  "status": "success",
  "execution_time_ms": 139.1,
  "route": {
    "start": "Los Angeles, CA, USA",
    "finish": "New York, NY, USA",
    "start_coordinates": { "lat": 34.0522, "lon": -118.2437 },
    "finish_coordinates": { "lat": 40.7128, "lon": -74.0060 },
    "total_distance_miles": 2793.67,
    "duration_formatted": "49 hrs, 54 mins",
    "duration_seconds": 179640
  },
  "summary": {
    "total_distance_miles": 2793.67,
    "total_fuel_consumed_gallons": 279.35,
    "total_fuel_cost_usd": 862.71,
    "number_of_fuel_stops": 7,
    "vehicle_range_miles": 500.0,
    "vehicle_mpg": 10.0,
    "average_fuel_price_usd": 3.088,
    "cost_per_mile_usd": 0.31,
    "optimization_strategy": "balanced_windowed_greedy"
  },
  "fuel_stops": [
    {
      "stop_number": 1,
      "station_id": 1410,
      "name": "Maverik #674",
      "address": "276.7 mi Exit",
      "city": "North Las Vegas",
      "state": "NV",
      "price_per_gallon": 3.282,
      "coordinates": { "lat": 36.1989, "lng": -115.1175 },
      "mile_marker": 276.7,
      "distance_from_last_stop_miles": 276.7,
      "gallons_refueled": 27.71,
      "cost_at_stop": 90.94,
      "fuel_level_on_arrival_percent": 44.7
    },
    {
      "stop_number": 2,
      "station_id": 693,
      "name": "MAVERIK COUNTRY STORE #693",
      "address": "I-70, EXIT 160",
      "city": "Green River",
      "state": "UT",
      "price_per_gallon": 3.282,
      "coordinates": { "lat": 38.9955, "lng": -110.1596 },
      "mile_marker": 678.2,
      "distance_from_last_stop_miles": 401.5,
      "gallons_refueled": 40.15,
      "cost_at_stop": 131.77,
      "fuel_level_on_arrival_percent": 19.7
    }
  ],
  "map": {
    "interactive_map_url": "http://127.0.0.1:8000/api/map-view/?start=Los%20Angeles,%20CA&finish=New%20York,%20NY...",
    "geojson": {
      "type": "FeatureCollection",
      "features": [...]
    }
  }
}
```

### 2. Interactive Map View
- **Endpoint**: `GET /api/map-view/?start=Los Angeles, CA&finish=New York, NY`
- Returns a full-screen interactive Leaflet map featuring the route line, green Start marker, red Destination marker, and numbered fuel station badges with cost breakdowns.

### 3. Health Check
- **Endpoint**: `GET /api/health/`
- Returns indexed station count and server status.

---

## 📬 Postman Testing

A ready-to-import Postman collection is located at:
`fuel_optimizer_postman_collection.json`

### Steps to Import:
1. Open **Postman**.
2. Click **Import** (top left).
3. Select `fuel_optimizer_postman_collection.json`.
4. Run any of the 7 pre-configured requests:
   - `1. Optimize Route - Cross Country (LA to NYC)`
   - `2. Optimize Route - Corner to Corner (Miami to Seattle)`
   - `3. Optimize Route - Midwest (Dallas to Chicago)`
   - `4. Optimize Route - GET Request (Query Params)`
   - `5. Short Route - Direct Trip (Austin to Dallas, <= 500 mi)`
   - `6. Cost-Optimal DP Strategy`
   - `7. Health Check Endpoint`