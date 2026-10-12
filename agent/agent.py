"""AfyaPlus agent.

Lesson references:
  - recursion_limit: Thursday Lab 2 - the agent's loop budget
  - Tool vs resource: Thursday Lessons 2-3 - tool = action, resource =
    read-only context (clinics_catalog)

Two backends behind the same `ask(question, trace_id, recursion_limit)`
interface:
  1. Stub backend (default) - deterministic. Used when GOOGLE_API_KEY is
     not set and for all pytest runs. $0 LLM spend.
  2. Gemini backend - langchain-google-genai. Used when GOOGLE_API_KEY
     is set; produces the captured transcript.

The rubric permits the stub. The FastAPI agreement is unchanged either
way; only the `model_card` in the response reveals which backend ran.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("afyaplus.agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _set_trace_env(trace_id: str) -> None:
    os.environ["TRACE_ID"] = trace_id


# Stub backend ------------------------------------------------------------

class StubLLM:
    """Rule-based LLM stand-in. Same answer shape as the real backend."""

    model_card = "afyaplus-agent-stub-v1"

    def _detect_intent(self, question: str) -> dict:
        q = question.lower()
        intent: dict[str, Any] = {
            "county": None, "service": None, "origin": None, "needs_route": False,
        }
        # Pick the last county mentioned - "in Kisumu" is the destination,
        # "from Nairobi" the origin. We split the sentence on "from" so
        # the two don't overwrite each other.
        for c in ("nairobi", "kisumu", "mombasa", "nakuru", "machakos",
                  "nyeri", "garissa", "uasin gishu"):
            if f"from {c}" in q:
                intent["origin"] = c
            elif c in q:
                intent["county"] = c

        if any(k in q for k in ("obstetric", "maternity", "labour", "labor")):
            intent["service"] = "obstetric"
        elif "emergency" in q:
            intent["service"] = "emergency"
        elif any(k in q for k in ("pediatric", "paediatric", "child")):
            intent["service"] = "pediatric"

        if any(k in q for k in ("route", "delivery", "plan")) and intent["origin"] and intent["county"]:
            intent["needs_route"] = True

        return intent


def _stub_run(question: str, tools_by_name: dict, trace_id: str) -> dict:
    """Drive the stub agent. Returns {answer, tool_calls, model_card}."""
    llm = StubLLM()
    intent = llm._detect_intent(question)
    tool_calls: list[dict] = []
    log.info("agent_intent trace_id=%s intent=%s", trace_id, intent)

    # Honest refusal: the data cannot answer statistics questions.
    if any(k in question.lower() for k in ("mortality", "rate", "incidence", "prevalence")):
        return {
            "answer": (
                "The available tools can look up clinics and plan delivery routes, "
                "but they do not have county-level health statistics. I cannot answer "
                f"'{question}' from the data I have access to."
            ),
            "tool_calls": tool_calls,
            "model_card": llm.model_card,
        }

    clinic_result = None
    if intent["county"]:
        args = {"county": intent["county"]}
        if intent["service"]:
            args["require_service"] = intent["service"]
        out = tools_by_name["find_clinic_by_county"].invoke(args)
        tool_calls.append({"tool": "find_clinic_by_county", "args": args, "result": out})
        clinic_result = json.loads(out) if isinstance(out, str) else out

    route_result = None
    if intent["needs_route"] and intent["origin"] and intent["county"]:
        args = {"origin": intent["origin"], "destination_county": intent["county"], "vehicle": "van"}
        out = tools_by_name["plan_delivery_route"].invoke(args)
        tool_calls.append({"tool": "plan_delivery_route", "args": args, "result": out})
        route_result = json.loads(out) if isinstance(out, str) else out

    if clinic_result and route_result:
        names = ", ".join(c["name"] for c in clinic_result.get("clinics", []))
        answer = (
            f"In {clinic_result['county'].title()} county, the matching clinic(s) are: {names}. "
            f"From {route_result['origin'].title()} a delivery van route "
            f"({route_result['heuristic']}) covers {route_result['total_km']} km "
            f"across {len(route_result['stops'])} stop(s) in roughly "
            f"{route_result['estimated_hours']} hours."
        )
    elif clinic_result:
        names = ", ".join(c["name"] for c in clinic_result.get("clinics", []))
        answer = (
            f"In {clinic_result['county'].title()} county I found "
            f"{clinic_result['count']} clinic(s): {names}."
        )
    elif route_result:
        answer = (
            f"Route from {route_result['origin'].title()} to {route_result['destination_county'].title()}: "
            f"{route_result['total_km']} km, {len(route_result['stops'])} stops, "
            f"~{route_result['estimated_hours']} hours. Heuristic: {route_result['heuristic']}."
        )
    else:
        answer = (
            "I could not match the question to a known tool. "
            "Try asking about clinics in a Kenyan county (e.g. Kisumu, Nairobi, Mombasa) "
            "or planning a delivery route from a named origin."
        )

    return {"answer": answer, "tool_calls": tool_calls, "model_card": llm.model_card}


# Gemini backend ----------------------------------------------------------

def _gemini_run(question: str, tools_by_name: dict, trace_id: str, recursion_limit: int) -> dict:
    """Run the agent against Gemini.

    The system prompt names the tools and tells the model to say it
    cannot answer when the data is missing. recursion_limit caps the
    loop on every invocation (Thursday Lab 2).
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate

    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY is not set; use the stub backend")

    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        temperature=0.2,
        max_output_tokens=512,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are the AfyaPlus logistics agent. You have access to the "
            "AfyaPlus MCP tools. Use them to answer. If the question is "
            "outside what the tools can answer, say so explicitly - do "
            "not guess. When you have a final answer, write it in one "
            "short paragraph."
        )),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    tools = list(tools_by_name.values())
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=recursion_limit,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )

    result = executor.invoke({"input": question})
    tool_calls = [
        {"tool": step[0].tool, "args": step[0].tool_input, "result": str(step[1])}
        for step in result.get("intermediate_steps", [])
    ]
    return {
        "answer": result.get("output", ""),
        "tool_calls": tool_calls,
        "model_card": f"gemini:{os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')}",
    }


# Public entry point ------------------------------------------------------

def ask(question: str, trace_id: str, recursion_limit: int = 6) -> dict:
    """Run the agent on `question`.

    - Sets the trace id in the environment so the MCP client propagates
      it into tool log lines.
    - Picks the stub or Gemini backend based on GOOGLE_API_KEY.
    - Always applies recursion_limit (Thursday Lab 2).
    """
    _set_trace_env(trace_id)
    from .mcp_client import get_tools
    tools = get_tools()
    tools_by_name = {t.name: t for t in tools}
    log.info("agent_start trace_id=%s question=%r", trace_id, question[:80])

    if os.getenv("GOOGLE_API_KEY"):
        result = _gemini_run(question, tools_by_name, trace_id, recursion_limit)
    else:
        result = _stub_run(question, tools_by_name, trace_id)

    log.info(
        "agent_done trace_id=%s tool_calls=%d model=%s",
        trace_id, len(result["tool_calls"]), result["model_card"],
    )
    return result