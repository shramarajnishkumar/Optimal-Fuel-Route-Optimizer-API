"""
Interactive Map Service using Folium and Leaflet.js.
Renders visual routes, custom markers for Start, Finish, and Fuel Stops with rich HTML popups.
Also outputs standard GeoJSON FeatureCollections for third-party consumers.
"""

import json
from typing import List, Dict, Any, Tuple
import folium
from folium import plugins


def generate_route_map(
    route_coords: List[List[float]],
    start_info: Dict[str, Any],
    finish_info: Dict[str, Any],
    fuel_stops: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """
    Builds a Folium interactive map HTML representation.
    route_coords: list of [lon, lat] from OSRM
    """
    if not route_coords:
        return ""

    # Folium expects [lat, lon]
    folium_coords = [[pt[1], pt[0]] for pt in route_coords]

    # Calculate center point
    mid_idx = len(folium_coords) // 2
    center_lat, center_lon = folium_coords[mid_idx]

    # Initialize map without default OSM tiles to prevent OSM 403 Tile Usage Policy block
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=5,
        tiles=None,
        control_scale=True,
    )

    # Base Tile Layers (100% free, no API key required, no rate-limit blocking)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom",
        name="Street Map (Esri)",
        max_zoom=19,
        control=True,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; USGS, NOAA",
        name="Topographic Map (Esri)",
        max_zoom=19,
        control=True,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community",
        name="Satellite View (Esri)",
        max_zoom=19,
        control=True,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
        attr='&copy; OpenStreetMap France | &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        name="OpenStreetMap (Standard)",
        max_zoom=20,
        subdomains="abc",
        control=True,
    ).add_to(m)




    # 1. Add Route Polyline (Glow effect with dual line)
    # Background shadow/glow line
    folium.PolyLine(
        folium_coords,
        weight=8,
        color="#1e3a8a",
        opacity=0.35,
    ).add_to(m)

    # Main vibrant route line
    folium.PolyLine(
        folium_coords,
        weight=4,
        color="#2563eb",
        opacity=0.9,
        tooltip=f"Route: {summary.get('total_distance_miles', 0)} miles",
    ).add_to(m)

    # 2. Start Marker (Green)
    start_lat = start_info.get("lat", folium_coords[0][0])
    start_lon = start_info.get("lon", folium_coords[0][1])
    start_name = start_info.get("display_name", "Start Location")

    start_popup_html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 200px; padding: 5px;">
        <h4 style="margin: 0 0 6px 0; color: #16a34a; display: flex; align-items: center; gap: 6px;">
            <span>🟢</span> <b>Start Point</b>
        </h4>
        <div style="font-size: 13px; color: #334155; margin-bottom: 4px;"><b>{start_name}</b></div>
        <div style="font-size: 12px; color: #64748b;">Coords: {start_lat:.4f}, {start_lon:.4f}</div>
        <div style="font-size: 12px; color: #16a34a; margin-top: 4px; font-weight: 600;">Full Tank: 500 Miles Range</div>
    </div>
    """
    folium.Marker(
        [start_lat, start_lon],
        popup=folium.Popup(start_popup_html, max_width=300),
        tooltip="Origin: " + start_name,
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)

    # 3. Finish Marker (Red)
    finish_lat = finish_info.get("lat", folium_coords[-1][0])
    finish_lon = finish_info.get("lon", folium_coords[-1][1])
    finish_name = finish_info.get("display_name", "Destination")

    finish_popup_html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 200px; padding: 5px;">
        <h4 style="margin: 0 0 6px 0; color: #dc2626; display: flex; align-items: center; gap: 6px;">
            <span>🏁</span> <b>Destination</b>
        </h4>
        <div style="font-size: 13px; color: #334155; margin-bottom: 4px;"><b>{finish_name}</b></div>
        <div style="font-size: 12px; color: #64748b;">Coords: {finish_lat:.4f}, {finish_lon:.4f}</div>
        <div style="font-size: 12px; color: #dc2626; margin-top: 4px; font-weight: 600;">Total Miles: {summary.get('total_distance_miles', 0)} mi</div>
    </div>
    """
    folium.Marker(
        [finish_lat, finish_lon],
        popup=folium.Popup(finish_popup_html, max_width=300),
        tooltip="Destination: " + finish_name,
        icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
    ).add_to(m)

    # 4. Fuel Stop Markers (Orange/Amber with detailed receipts)
    for stop in fuel_stops:
        stop_num = stop.get("stop_number", 1)
        st_lat = stop["coordinates"]["lat"]
        st_lng = stop["coordinates"]["lng"]
        name = stop.get("name", "Fuel Stop")
        city = stop.get("city", "")
        state = stop.get("state", "")
        price = stop.get("price_per_gallon", 0.0)
        gallons = stop.get("gallons_refueled", 0.0)
        cost = stop.get("cost_at_stop", 0.0)
        mile = stop.get("mile_marker", 0.0)
        leg_dist = stop.get("distance_from_last_stop_miles", 0.0)
        address = stop.get("address", "")

        stop_popup_html = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 240px; padding: 8px;">
            <div style="background: linear-gradient(135deg, #f97316, #ea580c); color: white; padding: 6px 10px; border-radius: 6px; margin-bottom: 8px; font-weight: bold; display: flex; justify-content: space-between;">
                <span>⛽ Fuel Stop #{stop_num}</span>
                <span>${price:.3f}/gal</span>
            </div>
            <div style="font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 2px;">{name}</div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">{address}, {city}, {state}</div>
            
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 8px; font-size: 12px; line-height: 1.6;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b;">Route Mile:</span>
                    <b>Mile {mile:.1f}</b>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b;">Leg Distance:</span>
                    <b>{leg_dist:.1f} mi</b>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b;">Fuel Added:</span>
                    <b>{gallons:.1f} gallons</b>
                </div>
                <hr style="border: 0; border-top: 1px dashed #cbd5e1; margin: 4px 0;">
                <div style="display: flex; justify-content: space-between; font-size: 13px; color: #ea580c;">
                    <b>Stop Cost:</b>
                    <b>${cost:.2f}</b>
                </div>
            </div>
        </div>
        """

        # Custom div icon with badge
        icon_html = f"""
        <div style="background: #ea580c; color: white; border: 2px solid white; border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.4);">
            {stop_num}
        </div>
        """
        custom_icon = folium.DivIcon(html=icon_html, icon_size=(28, 28), icon_anchor=(14, 14))

        folium.Marker(
            [st_lat, st_lng],
            popup=folium.Popup(stop_popup_html, max_width=320),
            tooltip=f"Stop #{stop_num}: {name} (${price:.3f}/gal)",
            icon=custom_icon,
        ).add_to(m)

    # 5. Add Stats Legend / HUD Control (Top Right)
    total_miles = float(summary.get("total_distance_miles", 0.0))

    total_cost = summary.get("total_fuel_cost_usd", summary.get("total_cost"))
    if total_cost is None:
        total_cost = sum(s.get("cost_at_stop", 0.0) for s in fuel_stops)
    total_cost = float(total_cost)

    total_gal = summary.get("total_fuel_consumed_gallons", summary.get("total_gallons"))
    if total_gal is None:
        total_gal = sum(s.get("gallons_refueled", 0.0) for s in fuel_stops)
    total_gal = float(total_gal)

    stops_count = summary.get("number_of_fuel_stops", summary.get("number_of_stops", len(fuel_stops)))

    avg_price = summary.get("average_fuel_price_usd", summary.get("average_price_per_gallon"))
    if avg_price is None:
        avg_price = (total_cost / total_gal) if total_gal > 0 else 0.0
    avg_price = float(avg_price)

    tank_range = float(summary.get("vehicle_range_miles", summary.get("tank_range_miles", 500.0)))
    mpg = float(summary.get("vehicle_mpg", summary.get("mpg", 10.0)))

    hud_html = f"""
    <div style="
        position: fixed;
        top: 15px;
        right: 15px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(8px);
        padding: 14px 18px;
        border-radius: 12px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
        border: 1px solid #e2e8f0;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        min-width: 220px;
    ">
        <div style="font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 8px; border-bottom: 2px solid #2563eb; padding-bottom: 4px;">
            🚛 Fuel Route Summary
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
            <div>
                <div style="color: #64748b; font-size: 11px;">TOTAL DISTANCE</div>
                <div style="font-size: 15px; font-weight: 700; color: #2563eb;">{total_miles:,.1f} mi</div>
            </div>
            <div>
                <div style="color: #64748b; font-size: 11px;">TOTAL FUEL COST</div>
                <div style="font-size: 15px; font-weight: 700; color: #16a34a;">${total_cost:,.2f}</div>
            </div>
            <div>
                <div style="color: #64748b; font-size: 11px;">FUEL STOPS</div>
                <div style="font-size: 15px; font-weight: 700; color: #ea580c;">{stops_count} stops</div>
            </div>
            <div>
                <div style="color: #64748b; font-size: 11px;">FUEL CONSUMED</div>
                <div style="font-size: 15px; font-weight: 700; color: #475569;">{total_gal:,.1f} gal</div>
            </div>
        </div>
        <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; text-align: center;">
            {tank_range:.0f} mi Range • {mpg:.0f} MPG • Avg ${avg_price:.3f}/gal
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(hud_html))

    # Add Layer Control
    folium.LayerControl().add_to(m)

    # Fit bounds to entire route
    m.fit_bounds([
        [min(p[0] for p in folium_coords), min(p[1] for p in folium_coords)],
        [max(p[0] for p in folium_coords), max(p[1] for p in folium_coords)],
    ])

    return m.get_root().render()


def generate_geojson(
    route_coords: List[List[float]],
    start_info: Dict[str, Any],
    finish_info: Dict[str, Any],
    fuel_stops: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Generates standard GeoJSON FeatureCollection for API responses."""
    features = []

    # 1. Route LineString
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": route_coords,
        },
        "properties": {
            "name": "Route",
            "distance_miles": summary.get("total_distance_miles", 0.0),
            "fuel_cost_usd": summary.get("total_fuel_cost_usd", summary.get("total_cost", 0.0)),
            "fuel_consumed_gallons": summary.get("total_fuel_consumed_gallons", summary.get("total_gallons", 0.0)),
            "fuel_stops_count": summary.get("number_of_fuel_stops", summary.get("number_of_stops", len(fuel_stops))),
        },
    })

    # 2. Start Point
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [start_info.get("lon"), start_info.get("lat")],
        },
        "properties": {
            "type": "start",
            "name": start_info.get("display_name"),
        },
    })

    # 3. Finish Point
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [finish_info.get("lon"), finish_info.get("lat")],
        },
        "properties": {
            "type": "finish",
            "name": finish_info.get("display_name"),
        },
    })

    # 4. Fuel Stops
    for stop in fuel_stops:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [stop["coordinates"]["lng"], stop["coordinates"]["lat"]],
            },
            "properties": {
                "type": "fuel_stop",
                "stop_number": stop["stop_number"],
                "station_id": stop["station_id"],
                "name": stop["name"],
                "address": stop["address"],
                "city": stop["city"],
                "state": stop["state"],
                "price_per_gallon": stop["price_per_gallon"],
                "gallons_refueled": stop["gallons_refueled"],
                "cost_at_stop": stop["cost_at_stop"],
                "mile_marker": stop["mile_marker"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
