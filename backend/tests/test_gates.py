"""
Proves the three gates in agent/gates.py are correct in isolation, with
no LLM call involved anywhere. If these pass, the "code-enforced, not
prompt-enforced" claim in the product brief is literally true.
"""

from agent.gates import (
    MIN_SOURCE_CONTENT_CHARS,
    SOURCE_GATE_DISCLAIMER,
    enforce_source_gate,
    filter_contradicted_signals,
    gate_signals,
    opener_gate_violations,
    opportunity_gate,
    source_is_usable,
)
from agent.state import CandidateSignal, InferredSignal, StatedFact


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


class TestOpenerGateViolations:
    def test_clean_opener_has_no_violations(self):
        opener = "Noticed you don't have online booking, worth a quick chat?"
        notes = "Small business, phone-only booking."
        assert opener_gate_violations(opener, notes, []) == []

    def test_ungrounded_referral_is_flagged(self):
        opener = "I was referred to your business by a trusted colleague."
        notes = "Small accounting practice, booked via phone/email."
        violations = opener_gate_violations(opener, notes, [])
        assert len(violations) == 1
        assert "referral" in violations[0]

    def test_grounded_referral_is_not_flagged(self):
        opener = "I was referred to you by a mutual contact."
        notes = "Referred by a customer of theirs."
        assert opener_gate_violations(opener, notes, []) == []

    def test_meeting_reference_always_flagged_even_if_in_notes(self):
        # There's no legitimate data source for "we already spoke" in a
        # cold-outreach product, this is fabricated whenever it appears.
        opener = "Great speaking with you on our call last week."
        notes = "We had a call last week and discussed pricing."
        violations = opener_gate_violations(opener, notes, [])
        assert any("prior call" in v for v in violations)

    def test_prospect_attribution_always_flagged_even_if_in_notes(self):
        # The opener is addressed TO the prospect, so "you" in the final
        # text means the prospect, "as you mentioned" implies the
        # prospect told the rep this, which never happened, regardless of
        # whether the underlying detail really is notes-derived.
        opener = "As you mentioned, the brand caters to women, men, and children."
        notes = "The brand caters to women, men, and children."
        violations = opener_gate_violations(opener, notes, [])
        assert any("said something to the rep" in v for v in violations)

    def test_prospect_attribution_variant_phrasing_is_flagged(self):
        opener = "Per your note, you're already booked solid most weeks."
        violations = opener_gate_violations(opener, "Booked solid most weeks.", [])
        assert any("said something to the rep" in v for v in violations)

    def test_rep_perspective_attribution_is_not_flagged(self):
        opener = "I understand you're already booked solid most weeks."
        assert opener_gate_violations(opener, "Booked solid most weeks.", []) == []

    def test_third_person_drift_after_referral_is_flagged(self):
        # Live case: a referral mentioned in the notes pulled the model into
        # describing the prospect to a third party for the rest of the
        # opener too, instead of addressing them directly.
        opener = (
            "I understand you were referred to Family Plumbing by one of "
            "their happy customers, and I'd love to discuss how they've "
            "maintained such a strong reputation."
        )
        notes = "Referred to Family Plumbing by one of their customers, a happy repeat client."
        violations = opener_gate_violations(opener, notes, [])
        assert any("third person" in v for v in violations)

    def test_bare_their_is_flagged(self):
        opener = "I understand their team is booked solid most weeks."
        violations = opener_gate_violations(opener, "Booked solid most weeks.", [])
        assert any("third person" in v for v in violations)

    def test_bare_them_is_flagged(self):
        opener = "I'd love to help them grow their online presence."
        violations = opener_gate_violations(opener, "some notes", [])
        assert any("third person" in v for v in violations)

    def test_second_person_referral_is_not_flagged(self):
        opener = "I understand a happy customer referred me to you, and I'd love to discuss how you've maintained such a strong reputation."
        notes = "Referred by a happy repeat client."
        assert opener_gate_violations(opener, notes, []) == []

    def test_ungrounded_greeting_name_is_flagged(self):
        opener = "Hi Sarah, noticed you don't have a pricing page."
        notes = "Small business, no pricing page."
        violations = opener_gate_violations(opener, notes, [])
        assert any("Sarah" in v for v in violations)

    def test_greeting_name_grounded_in_stated_facts_is_not_flagged(self):
        opener = "Hi Sarah, love what you're building."
        facts = [StatedFact(category="positioning", quote="Founded by Sarah in 2020.")]
        assert opener_gate_violations(opener, "", facts) == []

    def test_generic_greeting_is_not_flagged(self):
        opener = "Hi there, noticed you don't have online booking."
        assert opener_gate_violations(opener, "some notes", []) == []

    def test_multiple_violations_all_reported(self):
        opener = "Hi Sarah, great catching up on our call, you were referred by a friend."
        violations = opener_gate_violations(opener, "no relevant notes", [])
        assert len(violations) == 3

    def test_fabricated_referrer_name_is_flagged(self):
        # Live case: notes said only "referred by a mutual contact" (no
        # name given anywhere), and the opener invented "our mutual
        # contact, Alex", not caught by the greeting-name check since
        # it's not in a "Hi {Name}," greeting.
        opener = "I was referred to you by our mutual contact, Alex, and wanted to reach out."
        notes = "Was referred by a mutual contact."
        violations = opener_gate_violations(opener, notes, [])
        assert any("Alex" in v for v in violations)

    def test_referrer_name_grounded_in_notes_is_not_flagged(self):
        opener = "I was referred to you by John, and wanted to reach out."
        notes = "Referred by John, a customer of theirs."
        assert opener_gate_violations(opener, notes, []) == []

    def test_referrer_name_grounded_in_notes_via_recommend_root_is_not_flagged(self):
        opener = "You were recommended to us by Acme, one of your clients."
        notes = "Recommended by Acme, an existing client of theirs."
        assert opener_gate_violations(opener, notes, []) == []


class TestFilterContradictedSignals:
    def test_drops_no_social_signal_when_social_links_found(self):
        signals = [
            InferredSignal(
                signal_type="no_social_links",
                reasoning="No links to social media platforms were found.",
            )
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=["facebook.com", "instagram.com"], has_contact_link=False
        )
        assert result == []

    def test_keeps_no_social_signal_when_no_social_links_found(self):
        signals = [
            InferredSignal(
                signal_type="no_social_links",
                reasoning="No links to social media platforms were found.",
            )
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=[], has_contact_link=False
        )
        assert len(result) == 1

    def test_drops_no_contact_signal_when_contact_link_found(self):
        signals = [
            InferredSignal(
                signal_type="no_contact_info",
                reasoning="No contact information is available on the site.",
            )
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=[], has_contact_link=True
        )
        assert result == []

    def test_unrelated_signals_pass_through_unaffected(self):
        signals = [
            InferredSignal(signal_type="no_pricing_page", reasoning="No pricing shown anywhere."),
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=["facebook.com"], has_contact_link=True
        )
        assert len(result) == 1

    def test_mixed_batch_only_drops_contradicted_ones(self):
        signals = [
            InferredSignal(signal_type="no_pricing_page", reasoning="No pricing shown."),
            InferredSignal(
                signal_type="no_social_links", reasoning="No social media links present."
            ),
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=["linkedin.com"], has_contact_link=False
        )
        assert len(result) == 1
        assert result[0].signal_type == "no_pricing_page"

    def test_empty_batch_returns_empty(self):
        assert filter_contradicted_signals([], social_links_found=["x.com"], has_contact_link=True) == []

    def test_regression_model_acknowledged_evidence_but_contradicted_it_anyway(self):
        # Observed live: llama-3.1-8b-instant's own reasoning admitted the
        # evidence said social links were found, then proposed the signal
        # anyway with a hedge ("not visible on the website itself"), under
        # a signal_type the original narrower filter didn't match at all.
        signals = [
            InferredSignal(
                signal_type="no_links_to_social_media",
                reasoning=(
                    "Although social media links were found in the "
                    "CODE-VERIFIED EVIDENCE, they are not visible on the "
                    "website itself."
                ),
            )
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=["facebook.com"], has_contact_link=False
        )
        assert result == []

    def test_does_not_collide_with_legitimate_social_proof_signal(self):
        # "social proof" (i.e. testimonials/reviews) is a different,
        # legitimate signal our own prompt explicitly asks for, it must
        # not be dropped just because it contains the word "social".
        signals = [
            InferredSignal(
                signal_type="no_social_proof",
                reasoning="No customer testimonials or reviews are shown anywhere on the site.",
            )
        ]
        result = filter_contradicted_signals(
            signals, social_links_found=["facebook.com"], has_contact_link=False
        )
        assert len(result) == 1
