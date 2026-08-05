"""
Isolated test for Tool 3 (infer_opportunity_signals), the Opportunity
Gate, and the contradiction filter, so you can see exactly what each
stage rejects. Requires GROQ_API_KEY.

Usage (from /backend):
    GROQ_API_KEY=gsk_... PYTHONPATH=. .venv/bin/python scripts/test_infer_signals.py <url>
"""

import sys

from agent.gates import filter_contradicted_signals, gate_signals
from agent.tools import fetch_source, infer_opportunity_signals


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    fetched = fetch_source(url)
    if not fetched.succeeded:
        print(f"fetch_source failed for {url}: {fetched.error}")
        return

    print(f"url: {url}")
    print(f"social links found in <a href>: {fetched.social_links_found or '(none)'}")
    print(f"contact link (tel:/mailto:) found: {fetched.has_contact_link}")

    candidates = infer_opportunity_signals(
        fetched.raw_content or "",
        social_links_found=fetched.social_links_found,
        has_contact_link=fetched.has_contact_link,
    )
    print(f"\nraw candidates from the model (UNGATED): {len(candidates)}")
    for c in candidates:
        print(f"  candidate: signal_type={c.signal_type!r} reasoning={c.reasoning!r}")

    gated = gate_signals(candidates)
    print(f"\nafter the Opportunity Gate: {len(gated)} survived")

    final = filter_contradicted_signals(
        gated, fetched.social_links_found, fetched.has_contact_link
    )
    print(f"after the contradiction filter: {len(final)} survived")
    for s in final:
        print(f"  [INFERRED] {s.signal_type}: {s.reasoning}")

    dropped_by_gate = len(candidates) - len(gated)
    dropped_by_filter = len(gated) - len(final)
    if dropped_by_gate:
        print(f"\n{dropped_by_gate} candidate(s) rejected by the Opportunity Gate.")
    if dropped_by_filter:
        print(
            f"{dropped_by_filter} candidate(s) dropped by the contradiction "
            "filter (contradicted by code-verified link evidence)."
        )


if __name__ == "__main__":
    main()
