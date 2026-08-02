"""
Isolated test for Tool 2 (extract_stated_facts). Requires GROQ_API_KEY.

Usage (from /backend):
    GROQ_API_KEY=gsk_... PYTHONPATH=. .venv/bin/python scripts/test_extract_facts.py <url>
"""

import sys

from agent.tools import extract_stated_facts, fetch_source


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    fetched = fetch_source(url)
    if not fetched.succeeded:
        print(f"fetch_source failed for {url}: {fetched.error}")
        return

    facts = extract_stated_facts(fetched.raw_content or "")

    print(f"url: {url}")
    print(f"extracted {len(facts)} stated fact(s):\n")
    for fact in facts:
        print(f'  [{fact.category}] "{fact.quote}"')


if __name__ == "__main__":
    main()
