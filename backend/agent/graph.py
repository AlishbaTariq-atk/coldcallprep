"""
LangGraph wiring for the ColdCallPrep pipeline.

Pipeline: fetch_source -> [extract_stated_facts -> infer_opportunity_signals]
-> generate_brief. The middle two nodes are skipped entirely when the
Source Gate says the fetched content isn't usable — there's nothing to
extract facts or signals from if raw_content is empty/missing, so the
graph branches straight to generate_brief with empty facts/signals and
lets the Source Gate force the "built from your notes only" disclaimer
onto the result.

--- Why generate_brief runs as an isolated deepagents subagent ---

Every other node in this graph runs in one shared Python process with the
raw fetched HTML sitting in local variables (`state["raw_content"]`). If
generate_brief were just "another LLM call in the same chain," nothing
would stop a future edit to this file from accidentally handing it
raw_content directly, or from a shared conversation history letting
exploratory reasoning about the site leak into the brief. The whole
product claim — "nothing is stated as fact unless it's traceable to real
content, and the model can't introduce new claims at generation time" —
would then depend on us remembering to be careful every time this file
changes.

deepagents' subagent pattern makes that structurally impossible instead
of relying on our discipline. When the orchestrator's `task` tool invokes
the `brief_writer` subagent, deepagents resets the subagent's message
history to a single HumanMessage containing only the task description we
constructed (see `_validate_and_prepare_state` in
deepagents/middleware/subagents.py) — it does NOT inherit the
orchestrator's transcript. Combined with the fact that we never put
raw_content into any state the orchestrator holds in the first place,
brief_writer's context is guaranteed by the framework to be exactly what
tools.generate_brief() decided to pass it: pre-gated stated_facts,
pre-gated inferred_signals, and raw_notes. Nothing else is reachable, even
as this pipeline grows more tools or reasoning steps upstream later.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.gates import enforce_source_gate, gate_signals, source_is_usable
from agent.state import AgentState
from agent.tools import (
    extract_stated_facts,
    fetch_source,
    generate_brief,
    infer_opportunity_signals,
)


def fetch_source_node(state: AgentState) -> dict:
    result = fetch_source(state["url"])
    return {
        "fetch_succeeded": result.succeeded,
        "raw_content": result.raw_content,
    }


def extract_facts_node(state: AgentState) -> dict:
    facts = extract_stated_facts(state.get("raw_content") or "")
    return {"stated_facts": facts}


def infer_signals_node(state: AgentState) -> dict:
    candidates = infer_opportunity_signals(state.get("raw_content") or "")
    # THE OPPORTUNITY GATE is applied right here, in code, before anything
    # the model produced is allowed to persist in state.
    gated = gate_signals(candidates)
    return {"inferred_signals": gated}


def generate_brief_node(state: AgentState) -> dict:
    usable = source_is_usable(
        state.get("fetch_succeeded", False), state.get("raw_content")
    )
    brief_text = generate_brief(
        stated_facts=state.get("stated_facts", []),
        inferred_signals=state.get("inferred_signals", []),
        raw_notes=state.get("raw_notes", ""),
        source_usable=usable,
    )
    # THE SOURCE GATE, enforced in code as a final pass regardless of what
    # the subagent produced or whether it remembered to mention the gap.
    brief_text = enforce_source_gate(
        brief_text,
        fetch_succeeded=state.get("fetch_succeeded", False),
        raw_content=state.get("raw_content"),
    )
    return {"brief_text": brief_text}


def route_after_fetch(state: AgentState) -> str:
    """
    Public (no leading underscore) because main.py's progress-strip driver
    reuses this exact function to predict which node runs next — it must
    never diverge from the graph's own routing decision.
    """
    if source_is_usable(state.get("fetch_succeeded", False), state.get("raw_content")):
        return "extract_facts"
    return "generate_brief"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("fetch_source", fetch_source_node)
    graph.add_node("extract_facts", extract_facts_node)
    graph.add_node("infer_signals", infer_signals_node)
    graph.add_node("generate_brief", generate_brief_node)

    graph.add_edge(START, "fetch_source")
    graph.add_conditional_edges(
        "fetch_source",
        route_after_fetch,
        {"extract_facts": "extract_facts", "generate_brief": "generate_brief"},
    )
    graph.add_edge("extract_facts", "infer_signals")
    graph.add_edge("infer_signals", "generate_brief")
    graph.add_edge("generate_brief", END)

    return graph.compile()
