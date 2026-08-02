"""
Isolated test for Tool 1 (fetch_source) — no LLM, no API key required.

Usage (from /backend):
    PYTHONPATH=. .venv/bin/python scripts/test_fetch_source.py <url>
"""

import sys

from agent.tools import fetch_source


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = fetch_source(url)

    print(f"url:       {url}")
    print(f"succeeded: {result.succeeded}")
    if result.succeeded:
        content = result.raw_content or ""
        print(f"content length: {len(content)} chars")
        print(f"preview: {content[:300]!r}")
    else:
        print(f"error: {result.error}")


if __name__ == "__main__":
    main()
