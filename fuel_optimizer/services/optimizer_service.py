"""
Fuel optimization service implementing:
1. Balanced Windowed Greedy Strategy (Default: practical 250-480 mile legs, minimizing total cost)
2. Pure Cost-Optimal Dynamic Programming (DAG Shortest Path, mathematical minimum cost)
Calculates exact fuel purchased, leg distances, per-stop costs, and total money spent.
"""

import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def plan_fuel_stops(
    total_distance_miles: float,
    candidate_stations: List[Dict[str, Any]],
    tank_range_miles: float = 500.0,
    mpg: float = 10.0,
    strategy: str = "balanced",
) -> Dict[str, Any]:
    """
    Computes optimal fuel stops along the route.
    Returns:
      {
        'stops': [
            {
                'stop_number': int,
                'station_id': int,
                'name': str,
                'address': str,
                'city': str,
                'state': str,
                'price_per_gallon': float,
                'coordinates': {'lat': float, 'lng': float},
                'mile_marker': float,
                'leg_distance_miles': float,
                'gallons_refueled': float,
                'cost_at_stop': float,
                'fuel_level_arrival_percent': float,
            }, ...
        ],
        'summary': {
            'total_distance_miles': float,
            'total_gallons': float,
            'total_cost': float,
            'number_of_stops': int,
            'mpg': float,
            'tank_range_miles': float,
            'average_price_per_gallon': float,
            'cost_per_mile': float,
            'strategy_used': str,
        }
      }
    """
    total_gallons_needed = round(total_distance_miles / mpg, 2)

    # Edge Case: Distance is within single tank range (<= 500 miles)
    if total_distance_miles <= tank_range_miles:
        # Determine reference price for fuel consumed
        if candidate_stations:
            cheapest_st = min(candidate_stations, key=lambda s: s["price"])
            ref_price = cheapest_st["price"]
        else:
            ref_price = 3.250

        total_cost = round(total_gallons_needed * ref_price, 2)
        return {
            "stops": [],
            "message": f"Route distance ({total_distance_miles:.1f} mi) is within vehicle range ({tank_range_miles:.0f} mi). No intermediate fuel stops required.",
            "summary": {
                "total_distance_miles": round(total_distance_miles, 2),
                "total_gallons": total_gallons_needed,
                "total_cost": total_cost,
                "number_of_stops": 0,
                "mpg": mpg,
                "tank_range_miles": tank_range_miles,
                "average_price_per_gallon": round(ref_price, 3),
                "cost_per_mile": round(total_cost / max(total_distance_miles, 0.1), 3),
                "strategy_used": "direct_trip_no_stops_needed",
            },
        }

    if not candidate_stations:
        raise ValueError("No fuel stations found along the route corridor within range.")

    if strategy == "cost_optimal":
        return _plan_cost_optimal_dp(total_distance_miles, candidate_stations, tank_range_miles, mpg)
    else:
        return _plan_balanced_greedy(total_distance_miles, candidate_stations, tank_range_miles, mpg)


def _plan_balanced_greedy(
    total_distance: float,
    stations: List[Dict[str, Any]],
    max_range: float,
    mpg: float,
) -> Dict[str, Any]:
    """
    Balanced greedy strategy:
    Truck starts with a full tank (500 miles range).
    Travels along the route and looks ahead in a safe window (e.g. 250 to 480 miles).
    Chooses the lowest-priced station in that window to refuel back to 100%.
    Continues until destination is reachable on remaining fuel.
    Fuel for the final leg to destination is paid at the final stop.
    """
    stops: List[Dict[str, Any]] = []
    curr_mile = 0.0
    stop_idx = 1
    safety_buffer = 15.0  # Refuel at least 15 miles before running completely empty
    min_preferred_leg = 220.0

    while total_distance - curr_mile > max_range:
        window_max = curr_mile + max_range - safety_buffer
        window_min = curr_mile + min_preferred_leg

        # Candidate stations in desired window
        window = [s for s in stations if window_min <= s["mile_marker"] <= window_max]
        if not window:
            # Fallback to any station between curr_mile + 50 and window_max
            window = [s for s in stations if (curr_mile + 50.0) <= s["mile_marker"] <= window_max]
        if not window:
            # Emergency fallback: any reachable station ahead
            window = [s for s in stations if curr_mile < s["mile_marker"] <= curr_mile + max_range]

        if not window:
            raise ValueError(
                f"Fuel range exceeded at mile {curr_mile:.1f}. No stations reachable within next {max_range:.0f} miles."
            )

        # Select the most cost-effective station in window
        best_station = min(window, key=lambda s: s["price"])
        leg_distance = round(best_station["mile_marker"] - curr_mile, 2)
        gallons = round(leg_distance / mpg, 2)
        cost = round(gallons * best_station["price"], 2)
        arrival_fuel_pct = round(((max_range - leg_distance) / max_range) * 100.0, 1)

        stops.append({
            "stop_number": stop_idx,
            "station_id": best_station["station_id"],
            "name": best_station["name"],
            "address": best_station["address"],
            "city": best_station["city"],
            "state": best_station["state"],
            "price_per_gallon": best_station["price"],
            "coordinates": {"lat": best_station["lat"], "lng": best_station["lng"]},
            "mile_marker": best_station["mile_marker"],
            "distance_from_last_stop_miles": leg_distance,
            "gallons_refueled": gallons,
            "cost_at_stop": cost,
            "fuel_level_on_arrival_percent": arrival_fuel_pct,
        })

        curr_mile = best_station["mile_marker"]
        stop_idx += 1

    # Remaining distance from last stop to destination
    final_leg_miles = round(total_distance - curr_mile, 2)
    final_gallons = round(final_leg_miles / mpg, 2)
    last_stop_price = stops[-1]["price_per_gallon"] if stops else 3.250
    final_cost = round(final_gallons * last_stop_price, 2)

    # Attribute final leg fuel purchase to the last stop (as truck fills up to finish the trip)
    if stops:
        stops[-1]["gallons_refueled"] = round(stops[-1]["gallons_refueled"] + final_gallons, 2)
        stops[-1]["cost_at_stop"] = round(stops[-1]["cost_at_stop"] + final_cost, 2)
        stops[-1]["final_leg_to_destination_miles"] = final_leg_miles

    total_cost = round(sum(s["cost_at_stop"] for s in stops), 2)
    total_gallons = round(sum(s["gallons_refueled"] for s in stops), 2)
    avg_price = round(total_cost / max(total_gallons, 0.01), 3)

    return {
        "stops": stops,
        "summary": {
            "total_distance_miles": round(total_distance, 2),
            "total_gallons": total_gallons,
            "total_cost": total_cost,
            "number_of_stops": len(stops),
            "mpg": mpg,
            "tank_range_miles": max_range,
            "average_price_per_gallon": avg_price,
            "cost_per_mile": round(total_cost / max(total_distance, 0.1), 3),
            "strategy_used": "balanced_windowed_greedy",
        },
    }


def _plan_cost_optimal_dp(
    total_distance: float,
    stations: List[Dict[str, Any]],
    max_range: float,
    mpg: float,
) -> Dict[str, Any]:
    """
    Pure Dynamic Programming (DAG Shortest Path) to achieve the global mathematical minimum fuel cost.
    Evaluates all possible station-to-station hops <= max_range.
    """
    # Build node list: Node 0 = Start, Node 1..N = Stations, Node N+1 = Destination
    nodes = [{"id": 0, "mile": 0.0, "price": 0.0, "name": "START", "data": None}]
    for idx, s in enumerate(stations):
        nodes.append({
            "id": idx + 1,
            "mile": s["mile_marker"],
            "price": s["price"],
            "name": s["name"],
            "data": s,
        })
    dest_id = len(nodes)
    nodes.append({"id": dest_id, "mile": total_distance, "price": 0.0, "name": "DESTINATION", "data": None})

    num_nodes = len(nodes)
    min_cost = [float("inf")] * num_nodes
    parent = [-1] * num_nodes
    min_cost[0] = 0.0

    for j in range(1, num_nodes):
        for i in range(j):
            dist = nodes[j]["mile"] - nodes[i]["mile"]
            if dist > max_range or dist <= 0:
                continue
            # Leg cost
            if j == dest_id:
                # Last leg to destination fueled at node i
                cost = min_cost[i] + (dist / mpg) * nodes[i]["price"]
            elif i == 0:
                # First leg fueled at node j
                cost = (dist / mpg) * nodes[j]["price"]
            else:
                cost = min_cost[i] + (dist / mpg) * nodes[j]["price"]

            if cost < min_cost[j]:
                min_cost[j] = cost
                parent[j] = i

    if min_cost[dest_id] == float("inf"):
        raise ValueError("Could not find a feasible path to destination without exceeding 500-mile tank range.")

    # Reconstruct path
    path = []
    curr = dest_id
    while curr != -1:
        path.append(curr)
        curr = parent[curr]
    path.reverse()

    stop_node_indices = path[1:-1]
    stops = []
    prev_node = 0
    for idx, s_idx in enumerate(stop_node_indices, 1):
        st_data = nodes[s_idx]["data"]
        leg_dist = round(nodes[s_idx]["mile"] - nodes[prev_node]["mile"], 2)
        gal = round(leg_dist / mpg, 2)
        cost = round(gal * nodes[s_idx]["price"], 2)
        arrival_fuel_pct = round(((max_range - leg_dist) / max_range) * 100.0, 1)

        stops.append({
            "stop_number": idx,
            "station_id": st_data["station_id"],
            "name": st_data["name"],
            "address": st_data["address"],
            "city": st_data["city"],
            "state": st_data["state"],
            "price_per_gallon": st_data["price"],
            "coordinates": {"lat": st_data["lat"], "lng": st_data["lng"]},
            "mile_marker": st_data["mile_marker"],
            "distance_from_last_stop_miles": leg_dist,
            "gallons_refueled": gal,
            "cost_at_stop": cost,
            "fuel_level_on_arrival_percent": arrival_fuel_pct,
        })
        prev_node = s_idx

    # Final leg to destination
    final_leg_miles = round(total_distance - nodes[prev_node]["mile"], 2)
    final_gal = round(final_leg_miles / mpg, 2)
    final_cost = round(final_gal * nodes[prev_node]["price"], 2)

    if stops:
        stops[-1]["gallons_refueled"] = round(stops[-1]["gallons_refueled"] + final_gal, 2)
        stops[-1]["cost_at_stop"] = round(stops[-1]["cost_at_stop"] + final_cost, 2)
        stops[-1]["final_leg_to_destination_miles"] = final_leg_miles

    total_cost = round(min_cost[dest_id], 2)
    total_gallons = round(total_distance / mpg, 2)
    avg_price = round(total_cost / max(total_gallons, 0.01), 3)

    return {
        "stops": stops,
        "summary": {
            "total_distance_miles": round(total_distance, 2),
            "total_gallons": total_gallons,
            "total_cost": total_cost,
            "number_of_stops": len(stops),
            "mpg": mpg,
            "tank_range_miles": max_range,
            "average_price_per_gallon": avg_price,
            "cost_per_mile": round(total_cost / max(total_distance, 0.1), 3),
            "strategy_used": "cost_optimal_dynamic_programming",
        },
    }
