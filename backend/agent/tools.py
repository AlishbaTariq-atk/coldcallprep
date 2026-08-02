"""
The four single-purpose tools described in the product brief:

  1. fetch_source            — HTTP fetch only. Never touches an LLM.
  2. extract_stated_facts    — pulls direct quotes. Nothing else.
  3. infer_opportunity_signals — proposes CANDIDATE signals. These are
     UNGATED; callers must run them through agent.gates.gate_signals
     before trusting them anywhere else in the pipeline. This function
     does not gate its own output — see agent/graph.py for where that
     happens.
  4. generate_brief          — delegates ONLY the two genuinely generative
     pieces (company snapshot, outreach opener) to an isolated deepagents
     subagent; the stated-facts and inferred-signals sections are
     rendered directly from typed state, in code, with no LLM involved.
     See agent/graph.py's module docstring for why isolating the
     subagent's context is the right call here.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from agent.prompts import (
    BRIEF_ORCHESTRATOR_PROMPT,
    BRIEF_WRITER_SYSTEM_PROMPT,
    EXTRACT_FACTS_PROMPT,
    INFER_SIGNALS_PROMPT,
)
from agent.state import CandidateSignal, InferredSignal, StatedFact

# Groq-hosted model. llama-3.3-70b-versatile is the better default (more
# reliable structured-output formatting — see the json_mode fallback below)
# but has a low free-tier daily token cap; llama-3.1-8b-instant is what's
# active here to work within that during development. Swap this one
# constant if you change providers/models — nothing else in this file
# should need to change since we always pass an instantiated ChatGroq,
# not a bare string.
MODEL_NAME = "llama-3.1-8b-instant"


def _build_model() -> ChatGroq:
    return ChatGroq(model=MODEL_NAME, temperature=0)
FETCH_TIMEOUT_SECONDS = 10.0
USER_AGENT = "ColdCallPrepBot/0.1 (prospect research tool; single-page fetch)"
MAX_CONTENT_CHARS = 12000
STRUCTURED_OUTPUT_RETRY_ATTEMPTS = 3


# --- Tool 1: fetch_source ----------------------------------------------------


class FetchResult(BaseModel):
    succeeded: bool
    raw_content: str | None = None
    error: str | None = None


def fetch_source(url: str) -> FetchResult:
    """
    Fetch the given URL and return its visible text content, stripped of
    scripts/styles/markup. Never raises — any failure (timeout, DNS,
    non-2xx, connection refused) is captured as succeeded=False so the
    Source Gate can act on it instead of the request crashing the
    pipeline.
    """
    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return FetchResult(succeeded=False, error=str(exc))

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())

    return FetchResult(succeeded=True, raw_content=text)


# --- Tool 2: extract_stated_facts -------------------------------------------


class _StatedFactsResponse(BaseModel):
    facts: list[StatedFact]


def extract_stated_facts(
    raw_content: str, model: ChatGroq | None = None
) -> list[StatedFact]:
    """
    Pull direct quotes about services, positioning, and target audience
    from raw site text. Structured output enforces the category/quote
    shape; the "must be a direct quote, not a paraphrase" rule lives in
    the prompt, not in code — unlike the two gates, this one genuinely
    relies on the model following instructions.
    """
    llm = model or _build_model()
    # Smaller/faster models occasionally mangle the tool-call formatting
    # for structured output (observed live with llama-3.1-8b-instant on
    # verbose responses) — retry a couple of times before giving up,
    # since the same request can succeed on a subsequent attempt.
    structured_llm = llm.with_structured_output(
        _StatedFactsResponse, method="json_mode"
    ).with_retry(stop_after_attempt=STRUCTURED_OUTPUT_RETRY_ATTEMPTS)
    result = structured_llm.invoke(
        [
            {"role": "system", "content": EXTRACT_FACTS_PROMPT},
            {"role": "user", "content": raw_content[:MAX_CONTENT_CHARS]},
        ]
    )
    return result.facts


# --- Tool 3: infer_opportunity_signals --------------------------------------


class _CandidateSignalsResponse(BaseModel):
    signals: list[CandidateSignal]


def infer_opportunity_signals(
    raw_content: str, model: ChatGroq | None = None
) -> list[CandidateSignal]:
    """
    Propose opportunity signals based on what's missing or weak on the
    site. Output here is UNGATED — signal_type/reasoning may be
    incomplete or absent. This function intentionally does not filter its
    own output; agent/graph.py::infer_signals_node is what calls
    agent.gates.gate_signals on the result before it touches state.
    """
    llm = model or _build_model()
    structured_llm = llm.with_structured_output(
        _CandidateSignalsResponse, method="json_mode"
    ).with_retry(stop_after_attempt=STRUCTURED_OUTPUT_RETRY_ATTEMPTS)
    result = structured_llm.invoke(
        [
            {"role": "system", "content": INFER_SIGNALS_PROMPT},
            {"role": "user", "content": raw_content[:MAX_CONTENT_CHARS]},
        ]
    )
    return result.signals


# --- Tool 4: generate_brief --------------------------------------------------


class BriefNarrative(BaseModel):
    """
    The ONLY two things the brief_writer subagent is trusted to generate.
    Everything else in the final brief (stated facts, inferred signals)
    is rendered directly from typed state by _render_stated_facts /
    _render_inferred_signals below — no LLM transcription involved, so
    there's no chance of it relabeling a signal, merging two together, or
    pulling something in from raw_notes.
    """

    company_snapshot: str
    outreach_opener: str


def _build_brief_orchestrator():
    return create_deep_agent(
        model=_build_model(),
        tools=[],
        system_prompt=BRIEF_ORCHESTRATOR_PROMPT,
        subagents=[
            {
                "name": "brief_writer",
                "description": (
                    "Writes the company snapshot and outreach opener "
                    "from pre-gated stated facts and inferred signals."
                ),
                "system_prompt": BRIEF_WRITER_SYSTEM_PROMPT,
                "tools": [],
                "response_format": BriefNarrative,
            }
        ],
    )


def _render_stated_facts(stated_facts: list[StatedFact]) -> str:
    if not stated_facts:
        return "(none — no stated facts were extracted.)"
    return "\n".join(f'- [{f.category}] "{f.quote}"' for f in stated_facts)


def _render_inferred_signals(inferred_signals: list[InferredSignal]) -> str:
    if not inferred_signals:
        return "No opportunity signals were identified."
    return "\n".join(f"[INFERRED] {s.signal_type}: {s.reasoning}" for s in inferred_signals)


def generate_brief(
    stated_facts: list[StatedFact],
    inferred_signals: list[InferredSignal],
    raw_notes: str,
    source_usable: bool,
) -> str:
    """
    Writes the Prospect Brief. The company_snapshot and outreach_opener
    are delegated to an isolated deepagents subagent (see agent/graph.py
    for the full rationale on why that isolation matters); the stated
    facts and inferred signals sections are rendered directly from the
    already-gated typed data, in code, with no model involved. The only
    inputs forwarded to the subagent are the pre-gated facts/signals
    passed in as arguments here — never raw_content, never the upstream
    conversation.
    """
    facts_block = _render_stated_facts(stated_facts)
    signals_block = _render_inferred_signals(inferred_signals)
    notes_block = raw_notes.strip() or "(none provided)"

    task_description = (
        f"Source usable: {source_usable}\n\n"
        f"Stated facts (direct quotes):\n{facts_block}\n\n"
        f"Inferred signals (already gated — each has a type and reasoning):\n"
        f"{signals_block}\n\n"
        f"Rep's notes:\n{notes_block}\n\n"
        "Write the company_snapshot and outreach_opener now."
    )

    orchestrator = _build_brief_orchestrator()
    result = orchestrator.invoke({"messages": [HumanMessage(content=task_description)]})

    narrative = _extract_narrative(result)

    return (
        f"**Company Snapshot**\n{narrative.company_snapshot}\n\n"
        f"**What They Say About Themselves**\n{facts_block}\n\n"
        f"**Opportunity Signals**\n{signals_block}\n\n"
        f"**Outreach Opener**\n{narrative.outreach_opener}"
    )


def _extract_narrative(result: dict) -> BriefNarrative:
    """
    Don't trust the orchestrator's own final message to be a faithful,
    unedited relay of what the subagent wrote — extract the subagent's
    actual structured output directly from the ToolMessage the `task`
    call produced (deepagents JSON-serializes response_format results
    into that ToolMessage's content).
    """
    for message in reversed(result["messages"]):
        if isinstance(message, ToolMessage):
            return BriefNarrative.model_validate_json(str(message.content))

    raise RuntimeError(
        "brief_writer subagent was never invoked — no ToolMessage found in result"
    )
