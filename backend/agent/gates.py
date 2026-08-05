"""
The three code-enforced gates in this pipeline: Opportunity, Source, and
Opener. None is a prompt instruction the model is asked to follow, each
is a plain Python function with a real conditional, called AFTER the LLM
produces output and BEFORE that output is allowed into agent state or the
final brief. If the model misbehaves, these functions are what stop bad
output from reaching the user, not the model's own compliance.
"""

from __future__ import annotations

import re

from agent.state import CandidateSignal, InferredSignal, StatedFact

# --- Opportunity Gate -------------------------------------------------------

MIN_SOURCE_CONTENT_CHARS = 200


def opportunity_gate(candidate: CandidateSignal) -> InferredSignal | None:
    """
    THE OPPORTUNITY GATE.

    An inferred signal is only admitted if it carries BOTH a non-empty
    signal_type AND a non-empty reasoning string. Anything else, a missing
    field, an empty string, a whitespace-only string, is rejected here,
    regardless of what the LLM claimed the signal was. Returns None on
    rejection; callers must treat None as "drop this candidate."
    """
    signal_type = (candidate.signal_type or "").strip()
    reasoning = (candidate.reasoning or "").strip()

    if not signal_type or not reasoning:
        return None

    return InferredSignal(signal_type=signal_type, reasoning=reasoning)


def gate_signals(candidates: list[CandidateSignal]) -> list[InferredSignal]:
    """Apply the Opportunity Gate to a batch; only survivors come back."""
    gated: list[InferredSignal] = []
    for candidate in candidates:
        signal = opportunity_gate(candidate)
        if signal is not None:
            gated.append(signal)
    return gated


# --- Opportunity Gate: contradiction filter ---------------------------------
#
# Added after live testing caught infer_opportunity_signals claiming "no
# social media links" on a page that had working, visible social icons.
# The evidence block in the prompt (see agent/prompts.py) tells the model
# to trust code-verified link data over its own reading of the text, but
# a model can still ignore that instruction, observed live, worse than
# just ignored: the model's own reasoning text acknowledged "social media
# links were found in the CODE-VERIFIED EVIDENCE" and proposed the signal
# anyway ("...but they are not visible on the website itself"), under a
# signal_type ("no_links_to_social_media") that didn't match the first,
# narrower version of this filter's exact-phrase check at all. This is
# the hard backstop: keyword + negation matching, not exact phrases, so
# it can't be dodged by rewording, a signal contradicted by evidence is
# dropped in code, unconditionally, regardless of how the model phrases
# it or whether it complied with the prompt.

_NEGATION_WORDS = ("no ", "not ", "n't", "lack", "missing", "without", "none", "isn't", "aren't")


def _claims_absence(text: str, topic: str) -> bool:
    """Check whether text asserts that `topic` is absent.

    Args:
        text: Lowercased signal_type + reasoning to search.
        topic: Phrase to look for (e.g. "social media", "contact").

    Returns:
        True if `topic` appears alongside a negation word.
    """
    # Signal types are snake_case ("no_links_to_social_media"); normalize
    # underscores to spaces so a phrase match like "social media" finds it.
    normalized = text.replace("_", " ")
    return topic in normalized and any(neg in normalized for neg in _NEGATION_WORDS)


def filter_contradicted_signals(
    signals: list[InferredSignal],
    social_links_found: list[str],
    has_contact_link: bool,
) -> list[InferredSignal]:
    """
    Drops any signal whose type+reasoning claims something code-verified
    page evidence directly contradicts. Only checks the two topics
    actually observed failing live (social links, contact links), this
    is not a general fact-checker. Topic phrase is "social media"
    specifically, not bare "social", a signal about missing "social
    proof" (testimonials) is a different, legitimate signal our own
    prompt asks for, and must not collide with this filter.
    """
    filtered: list[InferredSignal] = []
    for signal in signals:
        text = f"{signal.signal_type} {signal.reasoning}".lower()
        if social_links_found and _claims_absence(text, "social media"):
            continue
        if has_contact_link and _claims_absence(text, "contact"):
            continue
        filtered.append(signal)
    return filtered


# --- Source Gate -------------------------------------------------------------

SOURCE_GATE_DISCLAIMER = "Built from your notes only, couldn't retrieve site content."


def source_is_usable(fetch_succeeded: bool, raw_content: str | None) -> bool:
    """
    THE SOURCE GATE, part 1: decides whether fetched site content is usable
    at all. False if the fetch failed outright, or if it "succeeded" but
    came back near-empty (below MIN_SOURCE_CONTENT_CHARS).
    """
    if not fetch_succeeded:
        return False
    if raw_content is None:
        return False
    if len(raw_content.strip()) < MIN_SOURCE_CONTENT_CHARS:
        return False
    return True


# Below this, content cleared the Source Gate's minimum (200 chars, enough
# to not be "notes only") but is still thin enough that it's likely a
# sparse or mostly-empty page rather than a real site with substance.
PARTIAL_CONTENT_THRESHOLD_CHARS = 1500


def source_status(fetch_succeeded: bool, raw_content: str | None) -> str:
    """
    A human-readable, three-tier read on how much site content this brief
    is actually grounded in, built on the same fetch_succeeded/content-
    length data as source_is_usable, just with one more cut point for a
    UI summary rather than a pass/fail gate.
    """
    if not source_is_usable(fetch_succeeded, raw_content):
        return "Notes only"
    assert raw_content is not None  # source_is_usable already checked this
    if len(raw_content.strip()) < PARTIAL_CONTENT_THRESHOLD_CHARS:
        return "Partial content"
    return "Full site content retrieved"


def enforce_source_gate(
    brief_text: str, fetch_succeeded: bool, raw_content: str | None
) -> str:
    """
    THE SOURCE GATE, part 2: forces the disclaimer onto the brief in code
    when the source isn't usable, rather than trusting the LLM to have
    remembered to say so. Idempotent, won't double-prepend if the
    disclaimer is already there.
    """
    if source_is_usable(fetch_succeeded, raw_content):
        return brief_text

    if brief_text.strip().startswith(SOURCE_GATE_DISCLAIMER):
        return brief_text

    return f"{SOURCE_GATE_DISCLAIMER}\n\n{brief_text}"


# --- Opener Gate --------------------------------------------------------------
#
# Added after live testing caught the brief_writer subagent fabricating
# specific claims in the outreach opener, first "our accounting practice"
# (confusing sender/prospect identity, fixed by prompting), then "I was
# referred to your business by a trusted colleague" when nothing in the
# rep's notes mentioned a referral at all. That second one survived THREE
# rounds of prompt tightening: a small/fast model has a real, demonstrated
# tendency to fabricate plausible cold-outreach boilerplate no matter how
# explicitly it's told not to. This gate is the code-level backstop for
# that specific, bounded class of fabrication, not a general hallucination
# detector, but a real check on concrete, observed failure patterns.
#
# The referrer-name check below was added after a further live case: notes
# said only "referred by a mutual contact" (no name given), and the opener
# invented "our mutual contact, Alex", a fabricated name attached to a
# real referral, not caught by the greeting-name check since it wasn't in
# a "Hi {Name}," greeting. Prompt-only instructions were tried first and
# failed on retest (see agent/prompts.py's outreach_opener attribution
# rule), same lesson as the other two patterns here.

REFERRAL_ROOTS = ("referr", "recommend", "introduc")

MEETING_REFERENCE_ROOTS = (
    "our call",
    "our conversation",
    "our meeting",
    "we spoke",
    "we discussed",
    "our chat",
    "spoke with you",
    "great speaking",
    "enjoyed our",
    "following up on our",
    "after our",
)

# Same reasoning as MEETING_REFERENCE_ROOTS, different failure shape: the
# opener is addressed TO the prospect, so "you" in the final text always
# means the prospect, never the rep. A phrase like "as you mentioned"
# reads, to the prospect, as a claim that THEY told the rep this, but
# there is no data source in this product for the prospect having said
# anything to the rep. This was observed live: a notes-derived detail
# (something the rep already knew, unrelated to the prospect) got
# rendered as "As you mentioned, the brand caters to...", nonsensical to
# a stranger receiving a cold email, and a symptom of the exact
# fact/inference blending this product exists to prevent. Prompt-only
# fixes for this class of mistake have already failed twice elsewhere in
# this file, same lesson applies here.
PROSPECT_ATTRIBUTION_ROOTS = (
    "as you mentioned",
    "as you noted",
    "as you said",
    "you mentioned that",
    "per your note",
    "per your message",
)

_GREETING_NAME_PATTERN = re.compile(r"\b(?:Hi|Hello|Hey)\s+([A-Z][a-zA-Z]+),")
# A referral-root word followed, within the same clause-ish window, by a
# capitalized name-like token, catches "referred by our mutual contact,
# Alex" without requiring a specific sentence structure. Bounded and
# heuristic by design, matching this file's other keyword+proximity
# checks, not a general named-entity extractor.
_REFERRAL_NAME_PATTERN = re.compile(
    r"\b(?:referr\w*|recommend\w*|introduc\w*)\w*\b[^.!?\n]{0,50}?\b([A-Z][a-z]+)\b"
)
_GENERIC_NAMES = {
    "there", "team", "i", "you", "we", "our", "your", "the", "this", "that",
    "us", "it", "they", "their",
}


def _contains_any(text: str, roots: tuple[str, ...]) -> bool:
    """Check whether text contains any of the given substrings (case-insensitive).

    Args:
        text: Text to search.
        roots: Substrings to look for.

    Returns:
        True if any substring in `roots` is present in `text`.
    """
    lowered = text.lower()
    return any(root in lowered for root in roots)


def _extract_candidate_name(text: str, pattern: re.Pattern) -> str | None:
    """Extract a capitalized name-like token matched by `pattern`, filtering out generic words.

    Args:
        text: Text to search.
        pattern: Compiled regex whose first capture group is the candidate name.

    Returns:
        The matched name, or None if there's no match or it's a generic word (e.g. "there", "team").
    """
    match = pattern.search(text)
    if not match:
        return None
    name = match.group(1)
    if name.lower() in _GENERIC_NAMES:
        return None
    return name


def _extract_greeting_name(text: str) -> str | None:
    """Extract the name in a "Hi {Name}," style greeting, if present and not generic."""
    return _extract_candidate_name(text, _GREETING_NAME_PATTERN)


def _extract_referral_name(text: str) -> str | None:
    """Extract a name attributed to a referral/recommendation, if present and not generic."""
    return _extract_candidate_name(text, _REFERRAL_NAME_PATTERN)


def opener_gate_violations(
    outreach_opener: str, raw_notes: str, stated_facts: list[StatedFact]
) -> list[str]:
    """
    THE OPENER GATE.

    Checks the outreach opener for concrete, previously-observed
    fabrication patterns (unsupported referral, fabricated prior meeting,
    a fabricated claim that the prospect said something to the rep, a
    greeted or referral-attributed name not present anywhere it was given
    to us) and verifies each is actually grounded in what the rep gave
    us. Returns a list of violation descriptions; an empty list means the
    opener passes. This targets a bounded, named set of risks, it is not
    a general hallucination detector, and claims outside these patterns
    are not checked here.
    """
    violations: list[str] = []

    if _contains_any(outreach_opener, REFERRAL_ROOTS) and not _contains_any(
        raw_notes, REFERRAL_ROOTS
    ):
        violations.append(
            "mentions a referral/recommendation not present in the rep's notes"
        )

    if _contains_any(outreach_opener, MEETING_REFERENCE_ROOTS):
        # There is no data source in this product for "a prior call or
        # meeting already happened", every prospect is a cold-outreach
        # target by definition, so this claim is fabricated whenever it
        # appears, regardless of what the notes say.
        violations.append(
            "implies a prior call/meeting/conversation that never happened"
        )

    if _contains_any(outreach_opener, PROSPECT_ATTRIBUTION_ROOTS):
        # Same "no prior exchange exists" reasoning as above, always a
        # violation regardless of notes content, see PROSPECT_ATTRIBUTION_ROOTS.
        violations.append(
            "implies the prospect said something to the rep, which never happened"
        )

    haystack = (raw_notes + " " + " ".join(f.quote for f in stated_facts)).lower()

    greeting_name = _extract_greeting_name(outreach_opener)
    if greeting_name and greeting_name.lower() not in haystack:
        violations.append(
            f'greets a specific name ("{greeting_name}") not present in '
            "the notes or stated facts"
        )

    referral_name = _extract_referral_name(outreach_opener)
    if referral_name and referral_name.lower() not in haystack:
        violations.append(
            f'names a specific referrer ("{referral_name}") not present in '
            "the notes or stated facts"
        )

    return violations
