"""
Isolated test for Tool 4 (generate_brief), feeds it hand-written fake
facts/signals directly, with NO real fetch involved, to prove it only
ever uses what it's explicitly handed. Also exercises the Opener Gate:
generate_brief runs every outreach_opener through
agent.gates.opener_gate_violations internally (retry once, then a
code-templated fallback) before returning, so a clean run here is proof
that gate passed. Requires GROQ_API_KEY.

Usage (from /backend):
    GROQ_API_KEY=gsk_... PYTHONPATH=. .venv/bin/python scripts/test_generate_brief.py
"""

from agent.gates import opener_gate_violations
from agent.state import InferredSignal, StatedFact
from agent.tools import generate_brief


def main() -> None:
    stated_facts = [
        StatedFact(category="services", quote="We provide 24/7 emergency plumbing and HVAC repair."),
        StatedFact(category="positioning", quote="Family owned and operated since 1998."),
        StatedFact(category="target_audience", quote="Serving homeowners across the Murrieta area."),
    ]
    inferred_signals = [
        InferredSignal(
            signal_type="no_booking_system",
            reasoning="No online scheduling widget or booking link found anywhere on the site, contact is phone-only.",
        ),
        InferredSignal(
            signal_type="no_pricing_page",
            reasoning="No pricing or rate information is listed on any page.",
        ),
    ]
    raw_notes = "Referred by a customer. Seems like an old-school outfit."

    result = generate_brief(
        stated_facts=stated_facts,
        inferred_signals=inferred_signals,
        raw_notes=raw_notes,
        source_usable=True,
    )

    print("company_snapshot:", result.company_snapshot)
    print()
    print("outreach_opener:", result.outreach_opener)

    # generate_brief already gated this internally, re-checking here just
    # makes that visible rather than trusting it silently happened.
    violations = opener_gate_violations(result.outreach_opener, raw_notes, stated_facts)
    print()
    print("Opener Gate violations on final output:", violations or "(none)")


if __name__ == "__main__":
    main()
