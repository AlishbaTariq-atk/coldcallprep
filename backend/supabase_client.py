"""
Writes a completed run to Supabase: one row in `prospects`, one row in
`briefs` (see supabase/migrations/0001_init.sql for the schema). Called
exactly once, from main.py, right when a run finishes, not from a
frontend poll, since a run can be polled many times after completion and
that would risk duplicate rows.

Uses the service-role key since this is a trusted server-side write with
no user session. RLS policies in the migration currently allow all
access anyway (single-user take-home demo), but the service-role key is
the correct choice regardless of policy shape for a backend process.
"""

from __future__ import annotations

import os

from supabase import Client, create_client

_client: Client | None = None


def _get_client() -> Client:
    """Return a lazily-created, process-wide Supabase client.

    Returns:
        A Supabase client authenticated with the service-role key.
    """
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def save_run(url: str, raw_notes: str, brief: dict) -> None:
    """Persist a completed run as one prospect row and one linked brief row.

    Args:
        url: The prospect URL that was researched.
        raw_notes: The rep's original notes for this prospect.
        brief: The brief dict, in the same shape main.py._serialize_result()
            builds for the API response, reused as-is rather than
            redefining the field list here.
    """
    client = _get_client()

    prospect_result = (
        client.table("prospects")
        .insert({"url": url, "raw_notes": raw_notes})
        .execute()
    )
    prospect_id = prospect_result.data[0]["id"]

    client.table("briefs").insert(
        {
            "prospect_id": prospect_id,
            "stated_facts": brief["stated_facts"],
            "inferred_signals": brief["inferred_signals"],
            "company_snapshot": brief["company_snapshot"],
            "outreach_opener": brief["outreach_opener"],
            "brief_text": brief["brief_text"],
            "fetch_succeeded": brief["fetch_succeeded"],
            "source_usable": brief["source_usable"],
        }
    ).execute()
