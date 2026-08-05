"""
Proves agent.tools.technical_signals() is correct in isolation, with no
LLM call involved, these signals are synthesized directly from measured
FetchResult values, not model output, so they're pure functions of
input data and fully testable without any network access.
"""

from agent.tools import FetchResult, SLOW_LOAD_THRESHOLD_SECONDS, technical_signals


def _fetch_result(**overrides) -> FetchResult:
    defaults = dict(
        succeeded=True,
        raw_content="some content",
        load_time_seconds=0.5,
        has_viewport_meta=True,
        mixed_content_count=0,
        broken_links_found=[],
    )
    defaults.update(overrides)
    return FetchResult(**defaults)


class TestSlowPageLoad:
    def test_flags_load_time_above_threshold(self):
        result = _fetch_result(load_time_seconds=SLOW_LOAD_THRESHOLD_SECONDS + 1.7)
        signals = technical_signals(result)
        assert any(s.signal_type == "slow_page_load" for s in signals)
        matched = next(s for s in signals if s.signal_type == "slow_page_load")
        assert "4.2" in matched.reasoning  # actual measured value appears in the text

    def test_does_not_flag_load_time_at_or_below_threshold(self):
        result = _fetch_result(load_time_seconds=SLOW_LOAD_THRESHOLD_SECONDS)
        signals = technical_signals(result)
        assert not any(s.signal_type == "slow_page_load" for s in signals)

    def test_fast_load_produces_no_signal(self):
        result = _fetch_result(load_time_seconds=0.3)
        signals = technical_signals(result)
        assert not any(s.signal_type == "slow_page_load" for s in signals)


class TestMobileViewport:
    def test_flags_missing_viewport_tag(self):
        result = _fetch_result(has_viewport_meta=False)
        signals = technical_signals(result)
        assert any(s.signal_type == "no_mobile_viewport_tag" for s in signals)

    def test_present_viewport_tag_produces_no_signal(self):
        result = _fetch_result(has_viewport_meta=True)
        signals = technical_signals(result)
        assert not any(s.signal_type == "no_mobile_viewport_tag" for s in signals)


class TestMixedContent:
    def test_flags_mixed_content_when_present(self):
        result = _fetch_result(mixed_content_count=3)
        signals = technical_signals(result)
        matched = next(s for s in signals if s.signal_type == "mixed_content_warnings")
        assert "3" in matched.reasoning

    def test_zero_mixed_content_produces_no_signal(self):
        result = _fetch_result(mixed_content_count=0)
        signals = technical_signals(result)
        assert not any(s.signal_type == "mixed_content_warnings" for s in signals)


class TestBrokenLinks:
    def test_flags_broken_links_when_found(self):
        result = _fetch_result(broken_links_found=["https://example.com/dead-page"])
        signals = technical_signals(result)
        matched = next(s for s in signals if s.signal_type == "broken_links_found")
        assert "example.com/dead-page" in matched.reasoning

    def test_no_broken_links_produces_no_signal(self):
        result = _fetch_result(broken_links_found=[])
        signals = technical_signals(result)
        assert not any(s.signal_type == "broken_links_found" for s in signals)


class TestTechnicalSignalsOverall:
    def test_healthy_site_produces_zero_signals(self):
        result = _fetch_result(
            load_time_seconds=0.4,
            has_viewport_meta=True,
            mixed_content_count=0,
            broken_links_found=[],
        )
        assert technical_signals(result) == []

    def test_unhealthy_site_produces_all_four_signals(self):
        result = _fetch_result(
            load_time_seconds=6.0,
            has_viewport_meta=False,
            mixed_content_count=2,
            broken_links_found=["https://example.com/broken"],
        )
        signals = technical_signals(result)
        assert len(signals) == 4
        assert {s.signal_type for s in signals} == {
            "slow_page_load",
            "no_mobile_viewport_tag",
            "mixed_content_warnings",
            "broken_links_found",
        }

    def test_every_produced_signal_passes_the_opportunity_gate(self):
        # technical_signals produces InferredSignal directly (already
        # gate-shaped), but this proves that shape genuinely satisfies
        # the gate's own rules rather than just assuming it by construction.
        from agent.gates import opportunity_gate
        from agent.state import CandidateSignal

        result = _fetch_result(
            load_time_seconds=6.0,
            has_viewport_meta=False,
            mixed_content_count=2,
            broken_links_found=["https://example.com/broken"],
        )
        for signal in technical_signals(result):
            candidate = CandidateSignal(
                signal_type=signal.signal_type, reasoning=signal.reasoning
            )
            assert opportunity_gate(candidate) is not None
