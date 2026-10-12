"""Agent tests - stub backend, hermetic, $0 spend."""

from __future__ import annotations

import os

import pytest

# Ensure stub backend is used regardless of host env
os.environ.pop("GOOGLE_API_KEY", None)

from agent.agent import ask


def test_stub_multi_tool_clinic_and_route():
    r = ask("Find an obstetric clinic in Kisumu and plan a delivery from Nairobi",
            trace_id="agent-test-1")
    assert r["model_card"].startswith("afyaplus-agent-stub")
    assert len(r["tool_calls"]) == 2
    tools_used = {tc["tool"] for tc in r["tool_calls"]}
    assert tools_used == {"find_clinic_by_county", "plan_delivery_route"}
    assert "Kisumu" in r["answer"]
    assert "Nairobi" in r["answer"]


def test_stub_single_tool_clinic_only():
    r = ask("Where is the nearest emergency clinic in Mombasa?",
            trace_id="agent-test-2")
    assert len(r["tool_calls"]) == 1
    assert r["tool_calls"][0]["tool"] == "find_clinic_by_county"
    assert "Mombasa" in r["answer"]


def test_stub_honest_failure_on_unanswerable():
    r = ask("What is the maternal mortality rate in Marsabit county?",
            trace_id="agent-test-3")
    assert r["tool_calls"] == []
    assert "cannot answer" in r["answer"].lower()


def test_recursion_limit_default_is_six():
    """The default recursion_limit is 6 - the agent's loop budget."""
    import inspect
    sig = inspect.signature(ask)
    assert sig.parameters["recursion_limit"].default == 6
    # annotation is a string under `from __future__ import annotations`
    assert sig.parameters["recursion_limit"].annotation == "int"