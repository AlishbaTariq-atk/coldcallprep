"""
LangGraph wiring for the ColdCallPrep pipeline.

Pipeline: fetch_source -> [extract_stated_facts -> infer_opportunity_signals]
-> generate_brief. The middle two nodes are skipped entirely when the
Source Gate says the fetched content isn't usable, there's nothing to
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
product claim, "nothing is stated as fact unless it's traceable to real
content, and the model can't introduce new claims at generation time",
would then depend on us remembering to be careful every time this file
changes.

deepagents' subagent pattern makes that structurally impossible instead
of relying on our discipline. `tools._build_brief_writer()` builds the
`brief_writer` subagent via deepagents' own `create_sub_agent`, and it is
invoked directly with a single HumanMessage containing only the task
description tools.generate_brief() constructed, no shared conversation
for it to inherit from, and raw_content was never put into any state that
call had access to in the first place. brief_writer's context is
guaranteed by the framework to be exactly what generate_brief() decided
to pass it: pre-gated stated_facts, pre-gated inferred_signals, and
raw_notes. Nothing else is reachable, even as this pipeline grows more
tools or reasoning steps upstream later.

--- Why there's no orchestrator agent in front of it ---

Earlier versions of this pipeline routed through a deepagents
orchestrator whose entire job was calling a `task` tool to delegate to
brief_writer, unconditionally, every time. That's a second LLM asked to
make a decision that was never actually in question, and it cost far
more than its prompt size suggested: measured live, the orchestrator hop
alone accounted for roughly 95 of ~100 seconds spent in this node, while
direct invocation of the same subagent, same prompt, same isolation
guarantee, completed in under 3 seconds for the full pipeline. The
isolation this section describes was never coming from the orchestrator;
it comes from create_sub_agent's fresh, framework-built message history
and from raw_content never being reachable from generate_brief() in the
first place. Removing the orchestrator removed a redundant, unconditional
delegation step, not the isolation itself.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.gates import (
    enforce_source_gate,
    filter_contradicted_signals,
    gate_signals,
    source_is_usable,
)
from agent.state import AgentState
from agent.tools import (
    FetchResult,
    extract_stated_facts,
    fetch_source,
    generate_brief,
    infer_opportunity_signals,
    technical_signals,
)


def fetch_source_node(state: AgentState) -> dict:
    """Fetch the prospect's URL and record the result and code-verified evidence into state.

    Args:
        state: Current graph state; only `url` is read.

    Returns:
        State updates: fetch result fields (success, raw content, social/contact
        links, load time, viewport/mixed-content/broken-link evidence).
    """
    result = fetch_source(state["url"])
    return {
        "fetch_succeeded": result.succeeded,
        "raw_content": result.raw_content,
        "social_links_found": result.social_links_found,
        "has_contact_link": result.has_contact_link,
        "load_time_seconds": result.load_time_seconds,
        "has_viewport_meta": result.has_viewport_meta,
        "mixed_content_count": result.mixed_content_count,
        "broken_links_found": result.broken_links_found,
    }


def extract_facts_node(state: AgentState) -> dict:
    """Extract direct-quote stated facts from the fetched page content.

    Args:
        state: Current graph state; only `raw_content` is read.

    Returns:
        State update: `stated_facts`.
    """
    facts = extract_stated_facts(state.get("raw_content") or "")
    return {"stated_facts": facts}


def infer_signals_node(state: AgentState) -> dict:
    """Propose opportunity signals, then apply the Opportunity Gate and contradiction filter.

    Also appends the code-only technical signals (slow load, missing viewport
    tag, mixed content, broken links) derived from fetch_source_node's evidence.

    Args:
        state: Current graph state; reads `raw_content`, `stated_facts`, the
            code-verified link evidence, and the technical evidence fields.

    Returns:
        State update: `inferred_signals`, containing only signals that
        survived the Opportunity Gate and the contradiction filter, plus any
        technical signals.
    """
    social_links_found = state.get("social_links_found", [])
    has_contact_link = state.get("has_contact_link", False)

    candidates = infer_opportunity_signals(
        state.get("raw_content") or "",
        stated_facts=state.get("stated_facts", []),
        social_links_found=social_links_found,
        has_contact_link=has_contact_link,
    )
    # THE OPPORTUNITY GATE is applied right here, in code, before anything
    # the model produced is allowed to persist in state.
    gated = gate_signals(candidates)
    # Hard backstop on top of the gate: drop any signal the model
    # produced despite code-verified evidence directly contradicting it
    # (e.g. "no social links" on a page with real social <a href>s).
    gated = filter_contradicted_signals(gated, social_links_found, has_contact_link)

    # Technical signals never touch the LLM at all, synthesized directly
    # from fetch_source's measured values (load time, viewport tag, mixed
    # content, broken links), so they can't be wrong the way a model's
    # guess could be.
    fetch_result = FetchResult(
        succeeded=state.get("fetch_succeeded", False),
        social_links_found=social_links_found,
        has_contact_link=has_contact_link,
        load_time_seconds=state.get("load_time_seconds", 0.0),
        has_viewport_meta=state.get("has_viewport_meta", True),
        mixed_content_count=state.get("mixed_content_count", 0),
        broken_links_found=state.get("broken_links_found", []),
    )
    gated = gated + technical_signals(fetch_result)

    return {"inferred_signals": gated}


def generate_brief_node(state: AgentState) -> dict:
    """Generate the brief narrative and enforce the Source Gate on the assembled text.

    Args:
        state: Current graph state; reads `stated_facts`, `inferred_signals`,
            `raw_notes`, `fetch_succeeded`, and `raw_content`.

    Returns:
        State update: `source_usable`, `company_snapshot`, `outreach_opener`,
        and the final `brief_text` (with the Source Gate disclaimer applied
        if the source wasn't usable).
    """
    usable = source_is_usable(
        state.get("fetch_succeeded", False), state.get("raw_content")
    )
    generated = generate_brief(
        stated_facts=state.get("stated_facts", []),
        inferred_signals=state.get("inferred_signals", []),
        raw_notes=state.get("raw_notes", ""),
        source_usable=usable,
    )
    # THE SOURCE GATE, enforced in code as a final pass regardless of what
    # the subagent produced or whether it remembered to mention the gap.
    # Applied to the full-document brief_text; the UI additionally renders
    # its own banner directly from source_usable, so the disclaimer isn't
    # solely dependent on this string ever being read by anyone.
    brief_text = enforce_source_gate(
        generated.brief_text,
        fetch_succeeded=state.get("fetch_succeeded", False),
        raw_content=state.get("raw_content"),
    )
    return {
        "source_usable": usable,
        "company_snapshot": generated.company_snapshot,
        "outreach_opener": generated.outreach_opener,
        "brief_text": brief_text,
    }


def route_after_fetch(state: AgentState) -> str:
    """Decide which node runs after fetch_source, based on the Source Gate.

    Public (no leading underscore) because main.py's progress-strip driver
    reuses this exact function to predict which node runs next, it must
    never diverge from the graph's own routing decision.

    Args:
        state: Current graph state; reads `fetch_succeeded` and `raw_content`.

    Returns:
        "extract_facts" if the fetched content is usable, otherwise
        "generate_brief" (skipping fact/signal extraction entirely).
    """
    if source_is_usable(state.get("fetch_succeeded", False), state.get("raw_content")):
        return "extract_facts"
    return "generate_brief"


def build_graph():
    """Wire and compile the ColdCallPrep pipeline graph.

    Returns:
        A compiled LangGraph graph: fetch_source -> [extract_facts ->
        infer_signals] -> generate_brief, branching per route_after_fetch.
    """
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
