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

    stated_facts: list[StatedFact]
    inferred_signals: list[InferredSignal]

    brief_text: str
