"""
Proves the two gates in agent/gates.py are correct in isolation, with no
LLM call involved anywhere. If these pass, the "code-enforced, not
prompt-enforced" claim in the product brief is literally true.
"""

from agent.gates import (
    MIN_SOURCE_CONTENT_CHARS,
    SOURCE_GATE_DISCLAIMER,
    enforce_source_gate,
    gate_signals,
    opportunity_gate,
    source_is_usable,
)
from agent.state import CandidateSignal


class TestOpportunityGate:
    def test_accepts_valid_candidate(self):
        candidate = CandidateSignal(
            signal_type="no_pricing_page",
            reasoning="No pricing page found anywhere on the site.",
        )
        result = opportunity_gate(candidate)
        assert result is not None
        assert result.signal_type == "no_pricing_page"
        assert result.reasoning == "No pricing page found anywhere on the site."

    def test_rejects_missing_reasoning(self):
        candidate = CandidateSignal(signal_type="no_pricing_page", reasoning=None)
        assert opportunity_gate(candidate) is None

    def test_rejects_missing_signal_type(self):
        candidate = CandidateSignal(signal_type=None, reasoning="Some reasoning")
        assert opportunity_gate(candidate) is None

    def test_rejects_empty_string_reasoning(self):
        candidate = CandidateSignal(signal_type="dated_design", reasoning="")
        assert opportunity_gate(candidate) is None

    def test_rejects_whitespace_only_reasoning(self):
        candidate = CandidateSignal(signal_type="dated_design", reasoning="   ")
        assert opportunity_gate(candidate) is None

    def test_rejects_whitespace_only_signal_type(self):
        candidate = CandidateSignal(signal_type="   ", reasoning="Valid reasoning here")
        assert opportunity_gate(candidate) is None

    def test_rejects_both_missing(self):
        candidate = CandidateSignal(signal_type=None, reasoning=None)
        assert opportunity_gate(candidate) is None

    def test_strips_surrounding_whitespace(self):
        candidate = CandidateSignal(
            signal_type="  no_booking_system  ",
            reasoning="  No calendar tool found.  ",
        )
        result = opportunity_gate(candidate)
        assert result is not None
        assert result.signal_type == "no_booking_system"
        assert result.reasoning == "No calendar tool found."


class TestGateSignals:
    def test_filters_mixed_batch_keeping_only_valid(self):
        candidates = [
            CandidateSignal(signal_type="no_pricing_page", reasoning="No pricing anywhere."),
            CandidateSignal(signal_type="dated_design", reasoning=None),  # rejected
            CandidateSignal(signal_type=None, reasoning="orphaned reasoning"),  # rejected
            CandidateSignal(
                signal_type="no_testimonials", reasoning="No customer quotes on the site."
            ),
        ]
        result = gate_signals(candidates)
        assert len(result) == 2
        assert [s.signal_type for s in result] == ["no_pricing_page", "no_testimonials"]

    def test_empty_batch_returns_empty_list(self):
        assert gate_signals([]) == []

    def test_all_rejected_returns_empty_list(self):
        candidates = [
            CandidateSignal(signal_type="x", reasoning=""),
            CandidateSignal(signal_type="", reasoning="y"),
        ]
        assert gate_signals(candidates) == []


class TestSourceIsUsable:
    def test_fetch_failed_is_unusable_even_with_content(self):
        assert source_is_usable(False, "plenty of content " * 50) is False

    def test_fetch_succeeded_but_none_content_is_unusable(self):
        assert source_is_usable(True, None) is False

    def test_fetch_succeeded_but_empty_content_is_unusable(self):
        assert source_is_usable(True, "") is False

    def test_fetch_succeeded_but_short_content_is_unusable(self):
        assert source_is_usable(True, "short") is False

    def test_content_just_under_threshold_is_unusable(self):
        content = "a" * (MIN_SOURCE_CONTENT_CHARS - 1)
        assert source_is_usable(True, content) is False

    def test_content_above_threshold_is_usable(self):
        content = "a" * (MIN_SOURCE_CONTENT_CHARS + 1)
        assert source_is_usable(True, content) is True


class TestEnforceSourceGate:
    def test_prepends_disclaimer_when_source_unusable(self):
        result = enforce_source_gate("Some brief text.", fetch_succeeded=False, raw_content=None)
        assert result.startswith(SOURCE_GATE_DISCLAIMER)
        assert "Some brief text." in result

    def test_leaves_brief_untouched_when_source_usable(self):
        brief = "Some brief text built from real quotes."
        content = "a" * (MIN_SOURCE_CONTENT_CHARS + 10)
        result = enforce_source_gate(brief, fetch_succeeded=True, raw_content=content)
        assert result == brief

    def test_does_not_double_prepend_if_already_present(self):
        already = f"{SOURCE_GATE_DISCLAIMER}\n\nSome brief text."
        result = enforce_source_gate(already, fetch_succeeded=False, raw_content=None)
        assert result.count(SOURCE_GATE_DISCLAIMER) == 1
