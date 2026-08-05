"""
Proves generate_brief's retry-then-fallback orchestration around the
Opener Gate works, without any real LLM call, the brief_writer is
mocked so this is deterministic and fast, unlike the live tests in
scripts/test_generate_brief.py.
"""

from unittest.mock import patch

from agent.tools import BriefNarrative, generate_brief

GOOD_NARRATIVE = BriefNarrative(
    company_snapshot="A small accounting practice.",
    outreach_opener="Noticed you're booked by phone/email rather than online scheduling.",
)

BAD_NARRATIVE = BriefNarrative(
    company_snapshot="A small accounting practice.",
    outreach_opener="I was referred to your business by a trusted colleague.",
)

RAW_NOTES = "Small accounting practice, phone/email booking only."


def test_clean_opener_passes_on_first_attempt():
    with patch("agent.tools._invoke_brief_writer", return_value=GOOD_NARRATIVE) as mock_invoke:
        result = generate_brief(
            stated_facts=[], inferred_signals=[], raw_notes=RAW_NOTES, source_usable=False
        )
        assert mock_invoke.call_count == 1
        assert result.outreach_opener == GOOD_NARRATIVE.outreach_opener


def test_retries_once_then_falls_back_if_still_violating():
    with patch("agent.tools._invoke_brief_writer", return_value=BAD_NARRATIVE) as mock_invoke:
        result = generate_brief(
            stated_facts=[], inferred_signals=[], raw_notes=RAW_NOTES, source_usable=False
        )
        assert mock_invoke.call_count == 2
        assert "referred" not in result.outreach_opener.lower()
        assert RAW_NOTES in result.outreach_opener


def test_recovers_if_retry_produces_a_clean_opener():
    with patch(
        "agent.tools._invoke_brief_writer", side_effect=[BAD_NARRATIVE, GOOD_NARRATIVE]
    ) as mock_invoke:
        result = generate_brief(
            stated_facts=[], inferred_signals=[], raw_notes=RAW_NOTES, source_usable=False
        )
        assert mock_invoke.call_count == 2
        assert result.outreach_opener == GOOD_NARRATIVE.outreach_opener


def test_fallback_opener_never_violates_the_gate_itself():
    from agent.gates import opener_gate_violations

    with patch("agent.tools._invoke_brief_writer", return_value=BAD_NARRATIVE):
        result = generate_brief(
            stated_facts=[], inferred_signals=[], raw_notes=RAW_NOTES, source_usable=False
        )
        assert opener_gate_violations(result.outreach_opener, RAW_NOTES, []) == []
