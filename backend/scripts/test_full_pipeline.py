"""
Runs the full graph end-to-end on one example prospect. Requires
GROQ_API_KEY.

Usage (from /backend):
    GROQ_API_KEY=gsk_... PYTHONPATH=. .venv/bin/python scripts/test_full_pipeline.py <url> "<notes>"
"""

import sys

from agent.graph import build_graph


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.866myfamily.com/"
    notes = sys.argv[2] if len(sys.argv) > 2 else "Referred by a customer, seems old-school."

    graph = build_graph()
    result = graph.invoke({"url": url, "raw_notes": notes})

    print(f"url: {url}")
    print(f"fetch_succeeded: {result.get('fetch_succeeded')}")
    print(f"source_usable (the Source Gate's actual verdict): {result.get('source_usable')}")
    print(f"social_links_found: {result.get('social_links_found')}")
    print(f"has_contact_link: {result.get('has_contact_link')}")
    print(f"stated_facts: {len(result.get('stated_facts', []))}")
    print(f"inferred_signals: {len(result.get('inferred_signals', []))}")
    print("\n--- brief_text ---\n")
    print(result.get("brief_text"))


if __name__ == "__main__":
    main()
