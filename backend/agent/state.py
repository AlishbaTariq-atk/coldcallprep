"""
Shared data shapes for the agent graph. Keep these in sync with
lib/types.ts on the frontend and the jsonb columns in
supabase/migrations/0001_init.sql.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pydantic import BaseModel

StatedFactCategory = Literal["services", "positioning", "target_audience"]


class StatedFact(BaseModel):
    """A direct quote pulled from the prospect's site. Never a paraphrase."""

    category: StatedFactCategory
    quote: str


class CandidateSignal(BaseModel):
    """
    Raw, ungated output from infer_opportunity_signals. Fields are optional
    because this represents whatever the LLM produced *before* the
    Opportunity Gate has had a chance to reject it — trusting it at this
    stage would defeat the point of having a gate.
    """

    signal_type: Optional[str] = None
    reasoning: Optional[str] = None


class InferredSignal(BaseModel):
    """
    A signal that has passed the Opportunity Gate: signal_type and
    reasoning are both guaranteed non-empty by construction (see
    agent/gates.py::opportunity_gate, the only place these get created).
    """

    signal_type: str
    reasoning: str


class AgentState(TypedDict, total=False):
    """LangGraph state shared across the fetch/extract/infer nodes."""

    url: str
    raw_notes: str

    fetch_succeeded: bool
    raw_content: Optional[str]
    # Code-verified evidence extracted from the page's real <a href>
    # attributes (not the visible-text-only raw_content) — ground truth
    # for the "no social links" / "no contact info" style signals, which
    # infer_opportunity_signals is unreliable at judging from text alone
    # since icon-only links have no visible text to read in the first
    # place. See agent/gates.py::filter_contradicted_signals.
    social_links_found: list[str]
    has_contact_link: bool
    # Also code-verified, also from fetch_source — feeds
    # agent.tools.technical_signals(), which turns these into signals
    # directly in code rather than asking the model to guess at them.
    load_time_seconds: float
    has_viewport_meta: bool
    mixed_content_count: int
    broken_links_found: list[str]

    stated_facts: list[StatedFact]
    inferred_signals: list[InferredSignal]

    source_usable: bool
    company_snapshot: str
    outreach_opener: str
    brief_text: str
