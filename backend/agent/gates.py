"""
The two code-enforced gates described in the product brief. Neither is a
prompt instruction the model is asked to follow — each is a plain Python
function with a real conditional, called AFTER the LLM produces output and
BEFORE that output is allowed into agent state or the final brief. If the
model misbehaves, these functions are what stop bad output from reaching
the user, not the model's own compliance.
"""

from __future__ import annotations

from agent.state import CandidateSignal, InferredSignal

# --- Opportunity Gate -------------------------------------------------------

MIN_SOURCE_CONTENT_CHARS = 200


def opportunity_gate(candidate: CandidateSignal) -> InferredSignal | None:
    """
    THE OPPORTUNITY GATE.

    An inferred signal is only admitted if it carries BOTH a non-empty
    signal_type AND a non-empty reasoning string. Anything else — a missing
    field, an empty string, a whitespace-only string — is rejected here,
    regardless of what the LLM claimed the signal was. Returns None on
    rejection; callers must treat None as "drop this candidate."
    """
    signal_type = (candidate.signal_type or "").strip()
    reasoning = (candidate.reasoning or "").strip()

    if not signal_type or not reasoning:
        return None

    return InferredSignal(signal_type=signal_type, reasoning=reasoning)


def gate_signals(candidates: list[CandidateSignal]) -> list[InferredSignal]:
    """Apply the Opportunity Gate to a batch; only survivors come back."""
    gated: list[InferredSignal] = []
    for candidate in candidates:
        signal = opportunity_gate(candidate)
        if signal is not None:
            gated.append(signal)
    return gated


# --- Source Gate -------------------------------------------------------------

SOURCE_GATE_DISCLAIMER = "Built from your notes only — couldn't retrieve site content."


def source_is_usable(fetch_succeeded: bool, raw_content: str | None) -> bool:
    """
    THE SOURCE GATE, part 1: decides whether fetched site content is usable
    at all. False if the fetch failed outright, or if it "succeeded" but
    came back near-empty (below MIN_SOURCE_CONTENT_CHARS).
    """
    if not fetch_succeeded:
        return False
    if raw_content is None:
        return False
    if len(raw_content.strip()) < MIN_SOURCE_CONTENT_CHARS:
        return False
    return True


def enforce_source_gate(
    brief_text: str, fetch_succeeded: bool, raw_content: str | None
) -> str:
    """
    THE SOURCE GATE, part 2: forces the disclaimer onto the brief in code
    when the source isn't usable, rather than trusting the LLM to have
    remembered to say so. Idempotent — won't double-prepend if the
    disclaimer is already there.
    """
    if source_is_usable(fetch_succeeded, raw_content):
        return brief_text

    if brief_text.strip().startswith(SOURCE_GATE_DISCLAIMER):
        return brief_text

    return f"{SOURCE_GATE_DISCLAIMER}\n\n{brief_text}"
