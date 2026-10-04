"""
Fuel Station Service to load, spatially index, and query truck stops along a highway route.
Uses Scipy KDTree for ultra-fast candidate station discovery (< 20ms).
"""

import logging
import os
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from django.conf import settings
from scipy.spatial import KDTree

from .routing_service import haversine_miles

logger = logging.getLogger(__name__)


class FuelStationService:
    _instance: Optional["FuelStationService"] = None

    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.coords_np: Optional[np.ndarray] = None
        self.kdtree: Optional[KDTree] = None
        self._load_data()

    @classmethod
    def get_instance(cls) -> "FuelStationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_data(self):
        """Loads pre-processed fuel stations CSV and initializes spatial KDTree index."""
        csv_path = getattr(settings, "PROCESSED_FUEL_STATIONS_CSV", None)
        if not csv_path or not os.path.exists(csv_path):
            # Fallback to local file relative to this directory if settings path not found
            alt_path = os.path.join(settings.BASE_DIR, "processed_fuel_stations.csv")
            if os.path.exists(alt_path):
                csv_path = alt_path
            else:
                raise FileNotFoundError(f"Processed fuel stations CSV not found at {csv_path}")

        logger.info(f"Loading fuel stations from {csv_path}...")
        self.df = pd.read_csv(csv_path)
        # Drop any records with missing lat/lng or price
        self.df = self.df.dropna(subset=["lat", "lng", "price"])
        self.df["price"] = pd.to_numeric(self.df["price"], errors="coerce")
        self.df["lat"] = pd.to_numeric(self.df["lat"], errors="coerce")
        self.df["lng"] = pd.to_numeric(self.df["lng"], errors="coerce")
        self.df = self.df.dropna(subset=["lat", "lng", "price"])

        # Create coordinate array: [lng, lat] to match GeoJSON / spatial queries
        self.coords_np = self.df[["lng", "lat"]].to_numpy()
        self.kdtree = KDTree(self.coords_np)
        logger.info(f"Loaded and indexed {len(self.df)} US fuel stations.")

    def find_candidate_stations(
        self,
        route_coords: List[List[float]],
        cum_dist: List[float],
        corridor_radius_miles: float = 5.0,
        cluster_bin_miles: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """
        Finds candidate fuel stations located within corridor_radius_miles of the route.
        Projects each station to its nearest point on the route to determine its mile_marker.
        Deduplicates stations within cluster_bin_miles to pick the best/cheapest representative.
        
        Returns sorted list of station dicts by mile_marker:
        [
          {
            'station_id': int,
            'name': str,
            'address': str,
            'city': str,
            'state': str,
            'price': float,
            'lat': float,
            'lng': float,
            'mile_marker': float,
            'dist_to_route': float
          },
          ...
        ]
        """
        if self.df is None or self.kdtree is None or not route_coords:
            return []

        # 1. Downsample route points to ~1 point every ~5-10 miles to query KDTree rapidly
        total_pts = len(route_coords)
        step = max(1, total_pts // 1200) if total_pts > 1200 else 1
        downsampled = route_coords[::step]

        # 1 degree latitude ~ 69 miles. Add margin for query radius
        query_deg_radius = (corridor_radius_miles / 69.0) + 0.08
        candidate_indices = set()
        for pt in downsampled:
            nearby = self.kdtree.query_ball_point(pt, r=query_deg_radius)
            candidate_indices.update(nearby)

        if not candidate_indices:
            return []

        candidate_df = self.df.iloc[list(candidate_indices)].copy()

        # 2. Build spatial KDTree on all route points to project stations to exact mile markers
        route_pts_np = np.array([[c[0], c[1]] for c in route_coords])
        route_tree = KDTree(route_pts_np)

        mile_markers = []
        perp_distances = []
        for _, row in candidate_df.iterrows():
            st_pt = [row["lng"], row["lat"]]
            dist_deg, idx = route_tree.query(st_pt)
            route_pt = route_coords[idx]
            dist_miles = haversine_miles(row["lat"], row["lng"], route_pt[1], route_pt[0])
            mile_markers.append(cum_dist[idx])
            perp_distances.append(dist_miles)

        candidate_df["mile_marker"] = mile_markers
        candidate_df["dist_to_route"] = perp_distances

        # 3. Filter strictly within corridor radius
        valid_candidates = candidate_df[candidate_df["dist_to_route"] <= corridor_radius_miles].copy()
        if valid_candidates.empty:
            # If nothing within strict radius, allow up to 15 miles
            valid_candidates = candidate_df[candidate_df["dist_to_route"] <= 15.0].copy()

        valid_candidates = valid_candidates.sort_values(by="mile_marker").reset_index(drop=True)

        # 4. Cluster stations at close proximity (e.g. at the same highway exit)
        # and keep the cheapest station per cluster
        if cluster_bin_miles > 0:
            valid_candidates["mile_bin"] = (valid_candidates["mile_marker"] // cluster_bin_miles) * cluster_bin_miles
            clustered = (
                valid_candidates.sort_values(by="price")
                .groupby("mile_bin", as_index=False)
                .first()
                .sort_values(by="mile_marker")
                .reset_index(drop=True)
            )
        else:
            clustered = valid_candidates

        results = []
        for _, r in clustered.iterrows():
            results.append({
                "station_id": int(r["station_id"]),
                "name": str(r["name"]),
                "address": str(r["address"]),
                "city": str(r["city"]),
                "state": str(r["state"]),
                "price": round(float(r["price"]), 3),
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "mile_marker": round(float(r["mile_marker"]), 2),
                "dist_to_route": round(float(r["dist_to_route"]), 2),
            })

        return results
