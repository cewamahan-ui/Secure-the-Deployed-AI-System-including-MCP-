"""Role-based access control for the AfyaPlus API and MCP surface
(Week 9, Deliverable 2).

Two groups, deliberately named in the matrix itself:

  * PARTNER_TOOLS  - what an external logistics partner may call over
    MCP. Small, read-only, allowlist-scoped (see
    mcp_server/clinics_allowlist.json).
  * OPERATIONS_TOOLS - internal dispatch/ops surface. Includes the
    route planner and the catalog.

Every check is deny-by-default: an unknown role, an unknown tool, or a
missing entry yields False. That is the "unknown role denied" row the
self-assessment asks for, and it is enforced by the fall-through in
`can()`, not by an allowlist someone can forget to update.

HTTP-layer mapping (triage_api):
  - /triage   requires role triage_nurse or dispatcher (authentication
    is unchanged from Week 6 - security ADDS authorisation)
  - /agent/ask requires role dispatcher (Week 6 rule, preserved)
  - MCP tools consult `can(role, tool_name)` before answering.
"""

from __future__ import annotations

PARTNER_TOOLS = frozenset({
    "find_clinic_by_county",
    "check_stock",
})

OPERATIONS_TOOLS = frozenset({
    "plan_delivery_route",
    "clinics_catalog",
    "agent_ask",
})

ALL_TOOLS = PARTNER_TOOLS | OPERATIONS_TOOLS

# role -> {tool -> allowed}. Roles absent here (e.g. "unknown", "")
# are denied everything by the fall-through in can().
ROLE_MATRIX: dict[str, dict[str, bool]] = {
    # External partner: the two smallest read-only tools, nothing else.
    "logistics_partner": {
        "find_clinic_by_county": True,
        "check_stock": True,
        "plan_delivery_route": False,   # internal routing logic
        "clinics_catalog": False,       # full list stays internal
        "agent_ask": False,
    },
    # Internal dispatcher: ops tools plus triage, no partner tools needed.
    "dispatcher": {
        "find_clinic_by_county": True,
        "check_stock": True,
        "plan_delivery_route": True,
        "clinics_catalog": True,
        "agent_ask": True,
    },
    # Clinical staff: read-only logistics context, no ops surface.
    "triage_nurse": {
        "find_clinic_by_county": True,
        "check_stock": False,
        "plan_delivery_route": False,
        "clinics_catalog": False,
        "agent_ask": False,
    },
    # Auditor: may read the catalog for review purposes, nothing else.
    "auditor": {
        "find_clinic_by_county": True,
        "check_stock": False,
        "plan_delivery_route": False,
        "clinics_catalog": True,
        "agent_ask": False,
    },
}


def can(role: str | None, tool: str) -> bool:
    """Deny-by-default authorisation check.

    Unknown role, unknown tool, or missing matrix entry -> False.
    """
    if not role or not tool:
        return False
    return bool(ROLE_MATRIX.get(role, {}).get(tool, False))


def allowed_tools(role: str | None) -> list[str]:
    """Every tool `role` may call. Useful for the /whoami surface."""
    if not role:
        return []
    row = ROLE_MATRIX.get(role, {})
    return sorted(t for t in ALL_TOOLS if row.get(t, False))


def role_group(tool: str) -> str:
    """Which group a tool belongs to: 'partner', 'operations', or 'unknown'."""
    if tool in PARTNER_TOOLS:
        return "partner"
    if tool in OPERATIONS_TOOLS:
        return "operations"
    return "unknown"


def matrix_as_table() -> str:
    """Plain-text matrix for the manager brief appendix."""
    tools = sorted(ALL_TOOLS)
    header = ["role"] + tools
    rows = [header]
    for role in sorted(ROLE_MATRIX):
        rows.append([role] + ["yes" if can(role, t) else "no" for t in tools])
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = [" | ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows]
    lines.insert(1, "-+-".join("-" * w for w in widths))
    return "\n".join(lines)


if __name__ == "__main__":
    print(matrix_as_table())
    # Fail-closed self-check, mirrors test_rbac.py.
    assert can("logistics_partner", "check_stock")
    assert not can("logistics_partner", "plan_delivery_route")
    assert not can("mystery_role", "check_stock")
    assert not can(None, "check_stock")
    assert not can("dispatcher", "nonexistent_tool")
    print("\nrbac self-check passed: unknown role denied, partner scope minimal.")
