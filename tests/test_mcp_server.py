"""MCP server tests - Week 9 hardened surface.

Covers the Week 6 happy paths (now allowlist-scoped) plus the Week 9
security contract: check_stock answers one clinic only, cannot dump a
county or the environment, and the catalog is projected to public keys.
"""

from __future__ import annotations

import json
import logging

import pytest

from mcp_server.server import (
    PUBLIC_CLINIC_KEYS,
    _load_allowlist,
    check_stock,
    clinics_catalog,
    find_clinic_by_county,
    plan_delivery_route,
)


# --------------------------------------------------------------------------
# Happy paths (Week 6 contract, now allowlist-scoped)
# --------------------------------------------------------------------------

def test_find_clinic_happy():
    r = find_clinic_by_county("Kisumu", "obstetric", trace_id="t1")
    assert r["count"] == 2
    assert {c["name"] for c in r["clinics"]} == {
        "Jaramogi Oginga Odinga Teaching & Referral Hospital",
        "Kisumu County Referral Hospital",
    }


def test_find_clinic_case_insensitive():
    r = find_clinic_by_county("KISUMU", trace_id="t2")
    assert r["count"] == 2


def test_find_clinic_returns_only_public_keys():
    """Smallest useful dict: no phone numbers, no coordinates for partners."""
    r = find_clinic_by_county("Nairobi", trace_id="t2b")
    assert r["count"] > 0
    for clinic in r["clinics"]:
        assert set(clinic.keys()) <= set(PUBLIC_CLINIC_KEYS)
        assert "phone" not in clinic
        assert "lat" not in clinic


def test_find_clinic_respects_allowlist():
    """CL-006 (Uasin Gishu) is deliberately NOT on the partner allowlist."""
    r = find_clinic_by_county("Uasin Gishu", trace_id="t2c")
    assert r["count"] == 0
    assert r["clinics"] == []


def test_find_clinic_invalid_unknown_county():
    """Deliberate invalid call. Errors are returned as data, never raised."""
    r = find_clinic_by_county("Atlantis", trace_id="t3")
    assert "error" in r
    assert "atlantis" in r["error"].lower()
    assert "known_counties" in r
    assert "kisumu" in r["known_counties"]


def test_find_clinic_invalid_empty():
    r = find_clinic_by_county("", trace_id="t4")
    assert r["error"] == "county is required"


def test_route_happy():
    r = plan_delivery_route("Nairobi", "Kisumu", "van", trace_id="t5")
    assert r["origin"] == "nairobi"
    assert r["destination_county"] == "kisumu"
    assert r["vehicle"] == "van"
    assert r["total_km"] > 0
    assert len(r["stops"]) == 2
    # heuristic is named honestly
    assert "nearest-neighbour" in r["heuristic"]
    assert "not optimal" in r["heuristic"]


def test_route_invalid_unknown_origin():
    r = plan_delivery_route("Timbuktu", "Kisumu", trace_id="t6")
    assert "error" in r
    assert "origin" in r["error"].lower()


def test_route_invalid_unknown_vehicle():
    r = plan_delivery_route("Nairobi", "Kisumu", "rocket", trace_id="t7")
    assert "error" in r
    assert "vehicle" in r["error"].lower()


def test_route_invalid_unknown_destination():
    r = plan_delivery_route("Nairobi", "Atlantis", trace_id="t8")
    assert "error" in r
    assert "destination" in r["error"].lower()


def test_resource_returns_allowlisted_catalog():
    cat = json.loads(clinics_catalog())
    assert isinstance(cat, list)
    allow = _load_allowlist()
    for c in cat:
        assert c["id"] in allow
        assert set(c.keys()) <= set(PUBLIC_CLINIC_KEYS)
        assert "phone" not in c


# --------------------------------------------------------------------------
# check_stock - the Week 9 security test
# --------------------------------------------------------------------------

def test_check_stock_happy_smallest_dict():
    r = check_stock("CL-003", "oxytocin 10iu", trace_id="s1")
    assert r == {"clinic_id": "CL-003", "item": "oxytocin 10iu", "units": 130}


def test_check_stock_cannot_dump_county_or_country():
    """One clinic, one item. No list mode exists - passing a county as
    the clinic_id yields an error, never a bulk answer."""
    r = check_stock("Kisumu", "oxytocin 10iu", trace_id="s2")
    assert "error" in r
    assert "units" not in r
    assert "clinics" not in r


def test_check_stock_not_allowlisted_denied_without_enumeration():
    """CL-006 exists in the data but is off the allowlist. The error
    names the bad id back and lists nothing valid."""
    r = check_stock("CL-006", "amoxicillin 500mg", trace_id="s3")
    assert "error" in r
    assert "allowlist" in r["error"]
    assert "CL-001" not in json.dumps(r)
    assert "known" not in r


def test_check_stock_unknown_item_error_data():
    r = check_stock("CL-001", "teleportation device", trace_id="s4")
    assert "error" in r
    assert r["clinic_id"] == "CL-001"


def test_check_stock_empty_args():
    assert "error" in check_stock("", "item", trace_id="s5")
    assert "error" in check_stock("CL-001", "", trace_id="s6")


def test_no_tool_returns_environment():
    """The 'if check_stock can dump a country you are not done' rule,
    asserted structurally: no response carries env-shaped content."""
    probes = [
        check_stock("CL-001", "amoxicillin 500mg"),
        find_clinic_by_county("Nairobi"),
        plan_delivery_route("Nairobi", "Kisumu"),
        clinics_catalog(),
    ]
    for payload in probes:
        blob = payload.lower() if isinstance(payload, str) else json.dumps(payload).lower()
        for needle in ("environ", "getenv", "aws_", "secret"):
            assert needle not in blob, f"response leaked {needle!r}: {payload!r}"


# --------------------------------------------------------------------------
# Logging contract
# --------------------------------------------------------------------------

def test_log_line_per_call(caplog):
    """One log line per call, with trace_id."""
    caplog.set_level(logging.INFO, logger="afyaplus.mcp")
    find_clinic_by_county("Nairobi", trace_id="trace-xyz")
    plan_delivery_route("Nairobi", "Kisumu", trace_id="trace-xyz")
    check_stock("CL-001", "oxytocin 10iu", trace_id="trace-xyz")
    matching = [
        r for r in caplog.records
        if r.name == "afyaplus.mcp" and "trace-xyz" in r.getMessage()
    ]
    assert len(matching) >= 3


def test_logs_never_carry_raw_arguments(caplog):
    """Week 3 logging lesson: tool args can carry user text; we log
    tool name + outcome only."""
    caplog.set_level(logging.INFO, logger="afyaplus.mcp")
    find_clinic_by_county("Nairobi", trace_id="trace-abc")
    for record in caplog.records:
        if record.name == "afyaplus.mcp":
            assert "Nairobi" not in record.getMessage()
