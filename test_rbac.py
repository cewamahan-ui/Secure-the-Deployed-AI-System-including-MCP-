"""RBAC tests (Week 9, Deliverable 2).

Run: pytest test_rbac.py -v
"""

from __future__ import annotations

import pytest

from rbac import (
    ALL_TOOLS,
    OPERATIONS_TOOLS,
    PARTNER_TOOLS,
    ROLE_MATRIX,
    allowed_tools,
    can,
    role_group,
)


# --------------------------------------------------------------------------
# Partner scope is minimal
# --------------------------------------------------------------------------

def test_partner_may_call_stock_and_lookup():
    assert can("logistics_partner", "check_stock")
    assert can("logistics_partner", "find_clinic_by_county")


def test_partner_may_not_call_operations_tools():
    assert not can("logistics_partner", "plan_delivery_route")
    assert not can("logistics_partner", "clinics_catalog")
    assert not can("logistics_partner", "agent_ask")


def test_every_partner_tool_is_read_only_smallest_scope():
    """Partner surface == PARTNER_TOOLS exactly."""
    assert allowed_tools("logistics_partner") == sorted(PARTNER_TOOLS)


# --------------------------------------------------------------------------
# Unknown roles and tools are denied (the fall-through, not a list entry)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["", "unknown", "root", "admin", None, "LOGISTICS_PARTNER"])
def test_unknown_role_denied_everything(role):
    for tool in ALL_TOOLS:
        assert can(role, tool) is False, f"role {role!r} must not call {tool}"


def test_known_role_unknown_tool_denied():
    assert not can("dispatcher", "wipe_database")
    assert not can("dispatcher", "")


# --------------------------------------------------------------------------
# Operations roles
# --------------------------------------------------------------------------

def test_dispatcher_has_full_ops_surface():
    assert allowed_tools("dispatcher") == sorted(ALL_TOOLS)


def test_triage_nurse_is_read_only_lookup():
    assert can("triage_nurse", "find_clinic_by_county")
    assert not can("triage_nurse", "check_stock")
    assert not can("triage_nurse", "plan_delivery_route")


def test_auditor_reads_catalog_only():
    assert can("auditor", "clinics_catalog")
    assert not can("auditor", "check_stock")
    assert not can("auditor", "agent_ask")


# --------------------------------------------------------------------------
# Matrix hygiene
# --------------------------------------------------------------------------

def test_groups_are_disjoint_and_covered():
    assert not (PARTNER_TOOLS & OPERATIONS_TOOLS)
    assert PARTNER_TOOLS | OPERATIONS_TOOLS == ALL_TOOLS


def test_every_role_row_covers_every_tool():
    for role, row in ROLE_MATRIX.items():
        assert set(row.keys()) == ALL_TOOLS, f"role {role} has an incomplete row"


def test_mcp_check_stock_mapping():
    assert role_group("check_stock") == "partner"
    assert role_group("plan_delivery_route") == "operations"
    assert role_group("definitely_not_a_tool") == "unknown"
