"""AfyaPlus MCP server - Week 9 hardened build.

Week 9 changes on top of the Week 6/7/8 server:

  1. New tool: check_stock(clinic_id, item). Scoped by
     mcp_server/clinics_allowlist.json. It returns the smallest useful
     dictionary ({clinic_id, item, units}) for ONE clinic, or an error
     dict. It cannot dump a county, a country, or the environment.
  2. The clinics://catalog resource is still read-only context, but it
     is filtered to the allowlisted clinic ids - a partner caller no
     longer sees the whole national list.
  3. Every tool validates its arguments and returns errors as data
     (never raises), so the agent can read and correct.

Tools:
  - find_clinic_by_county(county, require_service=None)
  - plan_delivery_route(origin, destination_county, vehicle="van")
  - check_stock(clinic_id, item)
Resource:
  - clinics://catalog   allowlisted clinics only

Run:  python -m mcp_server.server   (streamable-http on :8765)
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).parent / "data" / "clinics.json"
ALLOWLIST_PATH = Path(__file__).parent / "clinics_allowlist.json"
STOCK_PATH = Path(__file__).parent / "data" / "stock.json"

# Keys a partner caller may ever see in a clinic record. Deliberately
# excludes phone numbers - those are operational contact details, not
# data a partner tool needs to answer "is there an obstetric clinic?".
PUBLIC_CLINIC_KEYS = ("id", "name", "county", "services")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("afyaplus.mcp")


def _load_clinics() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_allowlist() -> set[str]:
    """Clinic ids this server is allowed to talk about. Fail closed."""
    try:
        with ALLOWLIST_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        ids = data.get("clinic_ids", [])
        if not isinstance(ids, list) or not ids:
            raise ValueError("clinic_ids must be a non-empty list")
        return {str(i) for i in ids}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # No allowlist, no tools. An empty allowlist would silently
        # widen scope; a missing one must narrow it to nothing.
        log.error("clinic allowlist unavailable, denying all clinic ids: %s", exc)
        return set()


def _load_stock() -> dict[str, dict]:
    with STOCK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


_KNOWN_COUNTIES: set[str] = {c["county"].lower() for c in _load_clinics()}

_KNOWN_ORIGINS: dict[str, tuple[float, float]] = {
    "nairobi": (-1.2921, 36.8219),
    "nairobi depot": (-1.2921, 36.8219),
    "mombasa": (-4.0435, 39.6682),
    "kisumu": (-0.0917, 34.7680),
}

_SPEED_KMH = {"van": 60, "ambulance": 80, "truck": 50}


def _public_clinic(record: dict) -> dict:
    """Project a clinic record down to the partner-visible keys."""
    return {k: record[k] for k in PUBLIC_CLINIC_KEYS if k in record}


def _log_call(tool: str, outcome: str, trace_id: str = "-") -> None:
    # Log the tool name and outcome only - never raw arguments, because
    # arguments may carry user-supplied text (Week 3 logging lesson).
    log.info("call tool=%s outcome=%s trace_id=%s", tool, outcome, trace_id)


def find_clinic_by_county(
    county: str,
    require_service: Optional[str] = None,
    trace_id: str = "-",
) -> dict:
    """Find clinics in a county, optionally filtered by service.

    Only allowlisted clinics are ever returned. Returns {count, clinics}
    on success or {error, known_counties} on bad input - errors as data.
    """
    if not county or not str(county).strip():
        _log_call("find_clinic_by_county", "error:empty_county", trace_id)
        return {"error": "county is required", "known_counties": sorted(_KNOWN_COUNTIES)}

    county_key = str(county).strip().lower()
    if county_key not in _KNOWN_COUNTIES:
        _log_call("find_clinic_by_county", "error:unknown_county", trace_id)
        return {"error": f"unknown county '{county}'", "known_counties": sorted(_KNOWN_COUNTIES)}

    allow = _load_allowlist()
    matches = [
        c for c in _load_clinics()
        if c["county"].lower() == county_key and c["id"] in allow
    ]
    if require_service:
        service_key = str(require_service).strip().lower()
        matches = [c for c in matches if service_key in {s.lower() for s in c["services"]}]

    _log_call("find_clinic_by_county", f"ok:{len(matches)}", trace_id)
    return {
        "county": county_key,
        "count": len(matches),
        "clinics": [_public_clinic(c) for c in matches],
    }


def plan_delivery_route(
    origin: str,
    destination_county: str,
    vehicle: str = "van",
    trace_id: str = "-",
) -> dict:
    """Plan a delivery route from a named origin to allowlisted clinics in a county.

    Nearest-neighbour greedy heuristic - decision support, NOT a
    guarantee of optimal routing (the docstring stays honest so the
    agent never overclaims). vehicle: van (default), ambulance, truck.
    """
    if not origin or not str(origin).strip():
        _log_call("plan_delivery_route", "error:empty_origin", trace_id)
        return {"error": "origin is required", "known_origins": sorted(_KNOWN_ORIGINS)}
    if not destination_county or not str(destination_county).strip():
        _log_call("plan_delivery_route", "error:empty_destination", trace_id)
        return {"error": "destination_county is required", "known_counties": sorted(_KNOWN_COUNTIES)}

    origin_key = str(origin).strip().lower()
    dest_key = str(destination_county).strip().lower()
    vehicle_key = (vehicle or "van").strip().lower()

    if origin_key not in _KNOWN_ORIGINS:
        _log_call("plan_delivery_route", "error:unknown_origin", trace_id)
        return {"error": f"unknown origin '{origin}'", "known_origins": sorted(_KNOWN_ORIGINS)}
    if dest_key not in _KNOWN_COUNTIES:
        _log_call("plan_delivery_route", "error:unknown_destination", trace_id)
        return {
            "error": f"unknown destination county '{destination_county}'",
            "known_counties": sorted(_KNOWN_COUNTIES),
        }
    if vehicle_key not in _SPEED_KMH:
        _log_call("plan_delivery_route", "error:unknown_vehicle", trace_id)
        return {"error": f"unknown vehicle '{vehicle}'", "known_vehicles": sorted(_SPEED_KMH)}

    allow = _load_allowlist()
    pool = [
        c for c in _load_clinics()
        if c["county"].lower() == dest_key and c["id"] in allow
    ]
    speed = _SPEED_KMH[vehicle_key]
    ox, oy = _KNOWN_ORIGINS[origin_key]

    stops: list[dict] = []
    cur_lat, cur_lon = ox, oy
    total_km = 0.0
    while pool:
        pool.sort(key=lambda c: _haversine_km(cur_lat, cur_lon, c["lat"], c["lon"]))
        nxt = pool.pop(0)
        leg = _haversine_km(cur_lat, cur_lon, nxt["lat"], nxt["lon"])
        total_km += leg
        # Smallest useful dictionary: id, name, leg distance. No phone
        # numbers, no coordinates for the partner view.
        stops.append({"clinic_id": nxt["id"], "name": nxt["name"], "leg_km": round(leg, 1)})
        cur_lat, cur_lon = nxt["lat"], nxt["lon"]

    _log_call("plan_delivery_route", f"ok:{len(stops)}_stops", trace_id)
    return {
        "origin": origin_key,
        "destination_county": dest_key,
        "vehicle": vehicle_key,
        "heuristic": "nearest-neighbour greedy, not optimal",
        "stops": stops,
        "total_km": round(total_km, 1),
        "estimated_hours": round(total_km / speed, 2) if speed else 0.0,
    }


def check_stock(clinic_id: str, item: str, trace_id: str = "-") -> dict:
    """Stock count for ONE allowlisted clinic and ONE item.

    Week 9 security test: this tool must never answer with a county, a
    country, or an environment dump. It returns
    {clinic_id, item, units} on success, or {error, ...} on bad input.
    There is deliberately no list mode.
    """
    if not clinic_id or not str(clinic_id).strip():
        _log_call("check_stock", "error:empty_clinic_id", trace_id)
        return {"error": "clinic_id is required"}
    if not item or not str(item).strip():
        _log_call("check_stock", "error:empty_item", trace_id)
        return {"error": "item is required"}

    clinic_key = str(clinic_id).strip().upper()
    item_key = str(item).strip().lower()
    allow = _load_allowlist()

    if clinic_key not in allow:
        # The error names the bad id back to the caller, nothing else.
        # It does NOT list valid ids - that would be a side channel for
        # enumerating the network.
        _log_call("check_stock", "error:not_allowlisted", trace_id)
        return {"error": f"clinic_id '{clinic_key}' is not on the partner allowlist"}

    stock = _load_stock().get(clinic_key, {})
    if item_key not in stock:
        _log_call("check_stock", "error:unknown_item", trace_id)
        return {"error": f"item '{item}' is not tracked at {clinic_key}", "clinic_id": clinic_key}

    _log_call("check_stock", "ok", trace_id)
    return {"clinic_id": clinic_key, "item": item_key, "units": stock[item_key]}


def clinics_catalog() -> str:
    """Allowlisted clinics only, projected to public keys."""
    allow = _load_allowlist()
    rows = [_public_clinic(c) for c in _load_clinics() if c["id"] in allow]
    return json.dumps(rows, indent=2)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Decision-support grade, not survey grade."""
    R = 6371.0
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def build_mcp_server():
    """Register tools/resources with FastMCP (network transport)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="afyaplus-mcp",
        instructions=(
            "Health logistics tools for AfyaPlus. find_clinic_by_county looks up "
            "allowlisted clinics, plan_delivery_route computes a greedy route, "
            "check_stock answers for one allowlisted clinic only. Errors are data."
        ),
    )

    @mcp.tool(
        name="find_clinic_by_county",
        description=(
            "Find allowlisted clinics in a Kenyan county, optionally filtered by "
            "service. Returns {count, clinics} or {error, known_counties} on bad input."
        ),
    )
    def t1(county: str, require_service: Optional[str] = None) -> dict:
        return find_clinic_by_county(county, require_service, os.environ.get("TRACE_ID", "-"))

    @mcp.tool(
        name="plan_delivery_route",
        description=(
            "Route from a named origin to allowlisted clinics in a county. Greedy "
            "nearest-neighbour, NOT optimal. vehicle: van/ambulance/truck."
        ),
    )
    def t2(origin: str, destination_county: str, vehicle: str = "van") -> dict:
        return plan_delivery_route(
            origin, destination_county, vehicle, os.environ.get("TRACE_ID", "-")
        )

    @mcp.tool(
        name="check_stock",
        description=(
            "Stock units for ONE allowlisted clinic and ONE item. "
            "Returns {clinic_id, item, units} or {error}. No list mode, no dumps."
        ),
    )
    def t3(clinic_id: str, item: str) -> dict:
        return check_stock(clinic_id, item, os.environ.get("TRACE_ID", "-"))

    @mcp.resource(
        uri="clinics://catalog",
        name="clinics_catalog",
        description="Allowlisted AfyaPlus clinics as JSON (read-only context).",
        mime_type="application/json",
    )
    def r1() -> str:
        return clinics_catalog()

    return mcp


def main() -> None:
    port = int(os.getenv("MCP_PORT", "8765"))
    mcp = build_mcp_server()
    mcp.settings.port = port
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
