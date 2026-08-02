"""
Isolated test for Tool 3 (infer_opportunity_signals) AND the Opportunity
Gate applied to its raw output, so you can see exactly what the gate
rejects vs admits. Requires GROQ_API_KEY.

Usage (from /backend):
    GROQ_API_KEY=gsk_... PYTHONPATH=. .venv/bin/python scripts/test_infer_signals.py <url>
"""

import sys

from agent.gates import gate_signals
from agent.tools import fetch_source, infer_opportunity_signals


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    fetched = fetch_source(url)
    if not fetched.succeeded:
        print(f"fetch_source failed for {url}: {fetched.error}")
        return

    candidates = infer_opportunity_signals(fetched.raw_content or "")
    print(f"url: {url}")
    print(f"raw candidates from the model (UNGATED): {len(candidates)}")
    for c in candidates:
        print(f"  candidate: signal_type={c.signal_type!r} reasoning={c.reasoning!r}")

    gated = gate_signals(candidates)
    print(f"\nafter the Opportunity Gate: {len(gated)} survived")
    for s in gated:
        print(f"  [INFERRED] {s.signal_type}: {s.reasoning}")

    rejected_count = len(candidates) - len(gated)
    if rejected_count:
        print(f"\n{rejected_count} candidate(s) were rejected by the gate.")


if __name__ == "__main__":
    main()
