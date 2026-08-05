"""
The four single-purpose tools described in the product brief:

  1. fetch_source: HTTP fetch only. Never touches an LLM.
  2. extract_stated_facts: pulls direct quotes. Nothing else.
  3. infer_opportunity_signals: proposes CANDIDATE signals. These are
     UNGATED; callers must run them through agent.gates.gate_signals
     before trusting them anywhere else in the pipeline. This function
     does not gate its own output, see agent/graph.py for where that
     happens.
  4. generate_brief: delegates ONLY the two genuinely generative
     pieces (company snapshot, outreach opener) to an isolated deepagents
     subagent; the stated-facts and inferred-signals sections are
     rendered directly from typed state, in code, with no LLM involved.
     See agent/graph.py's module docstring for why isolating the
     subagent's context is the right call here, and for why it's
     invoked directly rather than through a delegating orchestrator.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from deepagents.middleware.subagents import create_sub_agent
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from agent.gates import opener_gate_violations
from agent.prompts import (
    BRIEF_WRITER_SYSTEM_PROMPT,
    EXTRACT_FACTS_PROMPT,
    INFER_SIGNALS_PROMPT,
)
from agent.state import CandidateSignal, InferredSignal, StatedFact

# Groq-hosted model. 70B is more reliable at following strict negative
# constraints (identity confusion, fabrication) than the 8B fallback
# below, the Opener Gate exists as a code-level backstop regardless of
# which one is active, but a better baseline model means the gate has to
# do less work. Has a low free-tier daily token cap; swap to the 8B
# variant if that cap is hit.
#
# Read from GROQ_MODEL_NAME so the model can be swapped from Railway's
# dashboard (env var + restart) with no code push/redeploy, useful if
# the active model's rate limit gets hit close to a deadline.
DEFAULT_MODEL_NAME = "llama-3.1-8b-instant"
MODEL_NAME = os.environ.get("GROQ_MODEL_NAME", DEFAULT_MODEL_NAME)

# ChatGroq's own default for request_timeout is None, and the underlying
# groq SDK treats an *explicit* None as "disable the timeout entirely,"
# not "use a sane default" (that only happens when the argument is left
# unset). Left at the default, a single stalled request to Groq can hang
# this call forever, with no bound and nothing for the retry logic below
# to ever catch, since the call never returns to trigger a retry. This is
# a real, observed failure mode, not a theoretical one, every Groq call
# in this file must pass this explicitly.
REQUEST_TIMEOUT_SECONDS = 30.0


def _build_model(temperature: float = 0) -> ChatGroq:
    """Construct a Groq chat model instance.

    Args:
        temperature: Sampling temperature. Defaults to 0 (deterministic).

    Returns:
        A configured ChatGroq instance using MODEL_NAME, bounded by
        REQUEST_TIMEOUT_SECONDS.
    """
    return ChatGroq(
        model=MODEL_NAME, temperature=temperature, request_timeout=REQUEST_TIMEOUT_SECONDS
    )


FETCH_TIMEOUT_SECONDS = 15.0
# A single, legitimate, human-initiated page fetch (one rep, one URL, no
# crawling), using a realistic browser UA + headers here so ordinary bot
# -mitigation (Cloudflare/Radware, seen live on one of the example sites)
# doesn't false-positive-block it the way a bare httpx/library UA can.
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_CONTENT_CHARS = 12000
STRUCTURED_OUTPUT_RETRY_ATTEMPTS = 3
# Transient DNS/connection blips are common and shouldn't trip the Source
# Gate on their own, observed live: the same known-good URL failed on a
# first attempt and succeeded on a second, with nothing wrong with the
# site or the code. Only a fetch that fails on every attempt counts as a
# real failure.
FETCH_MAX_ATTEMPTS = 3
FETCH_RETRY_DELAY_SECONDS = 1.0

# Used to detect real social links from <a href> attributes directly,
# rather than asking the model to infer their absence from visible text.
# Icon-only social links (an <a> wrapping just an SVG, no visible text)
# are invisible to a text-only extraction, get_text() drops href
# entirely, which is exactly what caused a live, reported false
# "no social links" signal on a page that had working social icons.
SOCIAL_MEDIA_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "yelp.com",
    "pinterest.com",
)

# Technical checks below are all derived from data we already fetched (no
# extra requests) except the broken-link sample, which is deliberately
# bounded, a handful of same-origin links, short timeout, best-effort,
# so it stays cheap and can never meaningfully slow down or break the
# fetch itself. These exist to feed agent.tools.technical_signals(),
# which turns them into signals directly in code, no LLM opinion
# involved, unlike the rest of infer_opportunity_signals's output.
SLOW_LOAD_THRESHOLD_SECONDS = 2.5
BROKEN_LINK_SAMPLE_SIZE = 3
BROKEN_LINK_CHECK_TIMEOUT_SECONDS = 3.0


# --- Tool 1: fetch_source ----------------------------------------------------


class FetchResult(BaseModel):
    """Result of fetch_source: raw content plus code-verified page evidence."""

    succeeded: bool
    raw_content: str | None = None
    error: str | None = None
    social_links_found: list[str] = []
    has_contact_link: bool = False
    load_time_seconds: float = 0.0
    has_viewport_meta: bool = True
    mixed_content_count: int = 0
    broken_links_found: list[str] = []


def _check_sample_links_for_breakage(base_url: str, hrefs: list[str]) -> list[str]:
    """
    Best-effort: HEAD-checks up to BROKEN_LINK_SAMPLE_SIZE same-origin
    links found on the page. Never raises, any individual check that
    times out or errors is treated as "couldn't verify," not "broken,"
    since the goal is a cheap, honest signal, not a full link-audit tool.
    """
    origin = urlparse(base_url).netloc
    same_origin_links: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc != origin or parsed.scheme not in ("http", "https"):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        same_origin_links.append(absolute)
        if len(same_origin_links) >= BROKEN_LINK_SAMPLE_SIZE:
            break

    broken: list[str] = []
    for link in same_origin_links:
        try:
            with httpx.Client() as client:
                resp = client.head(
                    link,
                    timeout=BROKEN_LINK_CHECK_TIMEOUT_SECONDS,
                    headers=FETCH_HEADERS,
                    follow_redirects=True,
                )
            if resp.status_code >= 400:
                broken.append(link)
        except httpx.HTTPError:
            continue  # unverifiable, not counted as broken, avoid false positives
    return broken


def fetch_source(url: str) -> FetchResult:
    """
    Fetch the given URL and return its visible text content, stripped of
    scripts/styles/markup, plus code-verified evidence: social/contact
    links (from <a href> attributes, see SOCIAL_MEDIA_DOMAINS for why
    this can't come from text alone), page load time, presence of a
    mobile viewport meta tag, count of mixed-content (http:// on an
    https:// page) resource references, and a small best-effort sample
    of same-origin links checked for breakage. Never raises, any
    failure (timeout, DNS, non-2xx, connection refused) is captured as
    succeeded=False so the Source Gate can act on it instead of the
    request crashing the pipeline. Retries up to FETCH_MAX_ATTEMPTS times
    before giving up, only a fetch that fails on every attempt is
    treated as a real failure.
    """
    last_error: str | None = None

    for attempt in range(FETCH_MAX_ATTEMPTS):
        try:
            with httpx.Client(http2=True) as client:
                response = client.get(
                    url,
                    timeout=FETCH_TIMEOUT_SECONDS,
                    headers=FETCH_HEADERS,
                    follow_redirects=True,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            last_error = str(exc)
            if attempt < FETCH_MAX_ATTEMPTS - 1:
                time.sleep(FETCH_RETRY_DELAY_SECONDS)
            continue

        load_time_seconds = response.elapsed.total_seconds()
        soup = BeautifulSoup(response.text, "html.parser")

        hrefs = [a.get("href", "") or "" for a in soup.find_all("a", href=True)]
        social_links_found = sorted(
            {
                domain
                for domain in SOCIAL_MEDIA_DOMAINS
                if any(domain in href.lower() for href in hrefs)
            }
        )
        has_contact_link = any(
            href.lower().startswith(("tel:", "mailto:")) for href in hrefs
        )

        has_viewport_meta = soup.find("meta", attrs={"name": "viewport"}) is not None

        mixed_content_count = 0
        if urlparse(str(response.url)).scheme == "https":
            resource_urls = [
                tag.get(attr, "")
                for tag, attr in (
                    (t, "src") for t in soup.find_all(["img", "script"])
                )
            ] + [tag.get("href", "") for tag in soup.find_all("link")]
            mixed_content_count = sum(
                1 for u in resource_urls if u and u.lower().startswith("http://")
            )

        broken_links_found = _check_sample_links_for_breakage(str(response.url), hrefs)

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())

        return FetchResult(
            succeeded=True,
            raw_content=text,
            social_links_found=social_links_found,
            has_contact_link=has_contact_link,
            load_time_seconds=load_time_seconds,
            has_viewport_meta=has_viewport_meta,
            mixed_content_count=mixed_content_count,
            broken_links_found=broken_links_found,
        )

    return FetchResult(succeeded=False, error=last_error)


def technical_signals(fetch_result: FetchResult) -> list[InferredSignal]:
    """
    Synthesizes InferredSignal objects directly from FetchResult's
    technical fields, deliberately NOT going through the LLM at all.
    "Their site took 4.2s to load on this fetch" is a fact we measured;
    asking a model to eyeball text and guess at load time or a missing
    meta tag would just reintroduce the accuracy problem
    filter_contradicted_signals exists to catch elsewhere. Each check
    only produces a signal when the underlying condition is actually
    true, a fast, mobile-friendly, link-healthy site gets none of these,
    not a "no issues found" filler entry.
    """
    signals: list[InferredSignal] = []

    if fetch_result.load_time_seconds > SLOW_LOAD_THRESHOLD_SECONDS:
        signals.append(
            InferredSignal(
                signal_type="slow_page_load",
                reasoning=(
                    f"The site took {fetch_result.load_time_seconds:.1f}s to "
                    f"respond on this fetch, above the "
                    f"{SLOW_LOAD_THRESHOLD_SECONDS:.1f}s threshold for a "
                    "reasonably fast page, slow load times measurably hurt "
                    "conversion and search ranking."
                ),
            )
        )

    if not fetch_result.has_viewport_meta:
        signals.append(
            InferredSignal(
                signal_type="no_mobile_viewport_tag",
                reasoning=(
                    "No mobile viewport meta tag was found in the page "
                    "<head>, a strong indicator the site was never adapted "
                    "for mobile screens, where most local searches happen."
                ),
            )
        )

    if fetch_result.mixed_content_count > 0:
        signals.append(
            InferredSignal(
                signal_type="mixed_content_warnings",
                reasoning=(
                    f"{fetch_result.mixed_content_count} resource(s) on this "
                    "HTTPS page are loaded over plain HTTP, browsers flag "
                    "this as a security warning to visitors, which erodes "
                    "trust right at the point of first contact."
                ),
            )
        )

    if fetch_result.broken_links_found:
        count = len(fetch_result.broken_links_found)
        plural = "s" if count > 1 else ""
        signals.append(
            InferredSignal(
                signal_type="broken_links_found",
                reasoning=(
                    f"{count} link{plural} sampled on the page returned an "
                    f"error when checked directly (e.g. "
                    f"{fetch_result.broken_links_found[0]}), broken links "
                    "signal an unmaintained site to both visitors and "
                    "search engines."
                ),
            )
        )

    return signals


# --- Tool 2: extract_stated_facts -------------------------------------------


class _StatedFactsResponse(BaseModel):
    """Structured-output shape requested from the model in extract_stated_facts."""

    facts: list[StatedFact]


def extract_stated_facts(
    raw_content: str, model: ChatGroq | None = None
) -> list[StatedFact]:
    """
    Pull direct quotes about services, positioning, and target audience
    from raw site text. Structured output enforces the category/quote
    shape; the "must be a direct quote, not a paraphrase" rule lives in
    the prompt, not in code, unlike the two gates, this one genuinely
    relies on the model following instructions.
    """
    llm = model or _build_model()
    # Smaller/faster models occasionally mangle the tool-call formatting
    # for structured output (observed live with llama-3.1-8b-instant on
    # verbose responses), retry a couple of times before giving up,
    # since the same request can succeed on a subsequent attempt.
    structured_llm = llm.with_structured_output(
        _StatedFactsResponse, method="json_mode"
    ).with_retry(stop_after_attempt=STRUCTURED_OUTPUT_RETRY_ATTEMPTS)
    result = structured_llm.invoke(
        [
            {"role": "system", "content": EXTRACT_FACTS_PROMPT},
            {"role": "user", "content": raw_content[:MAX_CONTENT_CHARS]},
        ]
    )
    return result.facts


# --- Tool 3: infer_opportunity_signals --------------------------------------


class _CandidateSignalsResponse(BaseModel):
    """Structured-output shape requested from the model in infer_opportunity_signals."""

    signals: list[CandidateSignal]


def infer_opportunity_signals(
    raw_content: str,
    stated_facts: list[StatedFact] | None = None,
    social_links_found: list[str] | None = None,
    has_contact_link: bool = False,
    model: ChatGroq | None = None,
) -> list[CandidateSignal]:
    """
    Propose opportunity signals based on what's missing or weak on the
    site. Output here is UNGATED, signal_type/reasoning may be
    incomplete or absent. This function intentionally does not filter its
    own output; agent/graph.py::infer_signals_node is what calls
    agent.gates.gate_signals (and agent.gates.filter_contradicted_signals)
    on the result before it touches state.

    stated_facts is passed in specifically so the model can cross-
    reference the company's own claims against what else is actually on
    the page, an unsupported claim ("top 100," "5.0 stars") is a much
    stronger, more specific signal than a generic checklist item, but the
    model can only find it if it's given the claims to check.

    social_links_found / has_contact_link are code-verified evidence from
    fetch_source's real <a href> parsing, prepended as ground truth the
    model is told to trust over its own reading of the text, but since a
    model can still ignore that instruction (observed live), the caller
    additionally hard-filters any contradicted signal afterward rather
    than relying on the prompt alone.
    """
    social_links_found = social_links_found or []
    stated_facts = stated_facts or []

    facts_block = (
        _render_stated_facts(stated_facts)
        if stated_facts
        else "(none extracted, no claims to cross-reference)"
    )
    evidence_block = (
        "STATED FACTS (claims this company makes about itself elsewhere on "
        "the page, cross-reference these against the raw text below for "
        "unsupported-claim signals):\n"
        f"{facts_block}\n\n"
        "CODE-VERIFIED EVIDENCE (trust this over your own reading of the "
        "text below, it was extracted directly from the page's HTML "
        "links, not guessed from visible text):\n"
        f"- Social media links found on this page: "
        f"{', '.join(social_links_found) if social_links_found else 'none found'}\n"
        f"- A phone or email contact link (tel:/mailto:) was found on this "
        f"page: {'yes' if has_contact_link else 'no'}\n\n"
    )

    llm = model or _build_model()
    structured_llm = llm.with_structured_output(
        _CandidateSignalsResponse, method="json_mode"
    ).with_retry(stop_after_attempt=STRUCTURED_OUTPUT_RETRY_ATTEMPTS)
    result = structured_llm.invoke(
        [
            {"role": "system", "content": INFER_SIGNALS_PROMPT},
            {
                "role": "user",
                "content": evidence_block + raw_content[:MAX_CONTENT_CHARS],
            },
        ]
    )
    return result.signals


# --- Tool 4: generate_brief --------------------------------------------------


class BriefNarrative(BaseModel):
    """
    The ONLY two things the brief_writer subagent is trusted to generate.
    Everything else in the final brief (stated facts, inferred signals)
    is rendered directly from typed state by _render_stated_facts /
    _render_inferred_signals below, no LLM transcription involved, so
    there's no chance of it relabeling a signal, merging two together, or
    pulling something in from raw_notes.
    """

    company_snapshot: str
    outreach_opener: str


def _build_brief_writer(temperature: float = 0):
    """Build the isolated brief_writer subagent, invokable directly (no orchestrator).

    Uses deepagents' own create_sub_agent, the same construction path deepagents'
    task tool uses internally, so the subagent still gets a framework-built,
    freshly-invoked message history every call. What's gone is the separate
    orchestrator agent that used to sit in front of it purely to decide to
    delegate; that decision was never in question (BRIEF_ORCHESTRATOR_PROMPT
    always delegated unconditionally), so it was a full extra LLM round-trip
    for zero product value. See agent/graph.py's module docstring for the
    full rationale and the measured timing difference.

    Args:
        temperature: Sampling temperature passed to the underlying model.

    Returns:
        A Runnable that returns {"messages": [...], "structured_response": BriefNarrative}.
    """
    return create_sub_agent(
        {
            "name": "brief_writer",
            "description": (
                "Writes the company snapshot and outreach opener "
                "from pre-gated stated facts and inferred signals."
            ),
            "system_prompt": BRIEF_WRITER_SYSTEM_PROMPT,
            "tools": [],
            "model": _build_model(temperature),
        },
        response_format=BriefNarrative,
    )


def _render_stated_facts(stated_facts: list[StatedFact]) -> str:
    """Render stated facts as a plain-text bullet list for the brief_writer task description.

    Args:
        stated_facts: Gated facts to render.

    Returns:
        A newline-separated bullet list, or a placeholder string if empty.
    """
    if not stated_facts:
        return "(none, no stated facts were extracted.)"
    # Single quotes, not double: this text used to be JSON-argument-encoded
    # inside an orchestrator's `task` tool call, where unescaped double
    # quotes reliably triggered Groq's native tool-calling to emit
    # malformed `<function=...>` text (observed live on both the 8B and
    # 70B models). That specific path is gone now that brief_writer is
    # invoked directly, but there's no reason to reintroduce double quotes
    # for no benefit, so the safer format stays.
    return "\n".join(f"- [{f.category}] '{f.quote}'" for f in stated_facts)


def _render_inferred_signals(inferred_signals: list[InferredSignal]) -> str:
    """Render inferred signals as a plain-text list for the brief_writer task description.

    Args:
        inferred_signals: Gated signals to render.

    Returns:
        A newline-separated list, or a placeholder string if empty.
    """
    if not inferred_signals:
        return "No opportunity signals were identified."
    return "\n".join(f"[INFERRED] {s.signal_type}: {s.reasoning}" for s in inferred_signals)


class GeneratedBrief(BaseModel):
    """
    Full result of generate_brief. company_snapshot/outreach_opener come
    from the isolated subagent; brief_text is the assembled full-document
    string (used for Supabase storage / copy-all, see enforce_source_gate
    in graph.py, which operates on this field). The frontend renders each
    section from its own field rather than parsing brief_text, so the
    stated-fact/inferred-signal visual distinction never depends on
    string-parsing a markdown blob.
    """

    company_snapshot: str
    outreach_opener: str
    brief_text: str


OPENER_GATE_MAX_ATTEMPTS = 2


def generate_brief(
    stated_facts: list[StatedFact],
    inferred_signals: list[InferredSignal],
    raw_notes: str,
    source_usable: bool,
) -> GeneratedBrief:
    """
    Writes the Prospect Brief. The company_snapshot and outreach_opener
    are delegated to an isolated deepagents subagent (see agent/graph.py
    for the full rationale on why that isolation matters); the stated
    facts and inferred signals sections are rendered directly from the
    already-gated typed data, in code, with no model involved. The only
    inputs forwarded to the subagent are the pre-gated facts/signals
    passed in as arguments here, never raw_content, never the upstream
    conversation.

    The outreach_opener specifically passes through the OPENER GATE
    (agent.gates.opener_gate_violations) before it's trusted: if the
    subagent fabricates a referral, a prior meeting, or a named greeting
    not grounded in what it was given, we retry once with the violation
    named explicitly, and if it still fails, fall back to a plain
    code-templated opener that can never violate the gate. See
    agent/gates.py's module comment for why this exists, live testing
    caught this exact fabrication pattern surviving prompt-only fixes.
    """
    facts_block = _render_stated_facts(stated_facts)
    signals_block = _render_inferred_signals(inferred_signals)
    notes_block = raw_notes.strip() or "(none provided)"

    task_description = (
        f"Source usable: {source_usable}\n\n"
        f"Stated facts (direct quotes):\n{facts_block}\n\n"
        f"Inferred signals (already gated, each has a type and reasoning):\n"
        f"{signals_block}\n\n"
        f"Rep's notes:\n{notes_block}\n\n"
        "Write the company_snapshot and outreach_opener now."
    )

    narrative = _invoke_brief_writer(task_description)
    violations = opener_gate_violations(narrative.outreach_opener, raw_notes, stated_facts)

    attempt = 1
    while violations and attempt < OPENER_GATE_MAX_ATTEMPTS:
        correction = (
            f"{task_description}\n\n"
            "Your previous outreach_opener was REJECTED for these specific "
            f"reasons: {'; '.join(violations)}. Write a new outreach_opener "
            "that fixes this, do not repeat the same claim in any form."
        )
        narrative = _invoke_brief_writer(correction)
        violations = opener_gate_violations(narrative.outreach_opener, raw_notes, stated_facts)
        attempt += 1

    if violations:
        # Code-level fallback: never let a gate-failing opener reach the
        # user, even after a retry. This is deliberately plain rather
        # than clever, it can't fabricate anything because it doesn't
        # generate anything, just relays the notes verbatim.
        narrative = BriefNarrative(
            company_snapshot=narrative.company_snapshot,
            outreach_opener=_fallback_opener(raw_notes),
        )

    brief_text = (
        f"**Company Snapshot**\n{narrative.company_snapshot}\n\n"
        f"**What They Say About Themselves**\n{facts_block}\n\n"
        f"**Opportunity Signals**\n{signals_block}\n\n"
        f"**Outreach Opener**\n{narrative.outreach_opener}"
    )

    return GeneratedBrief(
        company_snapshot=narrative.company_snapshot,
        outreach_opener=narrative.outreach_opener,
        brief_text=brief_text,
    )


BRIEF_WRITER_MAX_ATTEMPTS = 3
# Kept from the orchestrator-based version: live testing there showed
# failures at temperature=0 weren't transient, the model reproduced the
# identical malformed output on every unchanged retry, so only resampling
# at a different temperature had a real chance of succeeding. Direct
# invocation removes the specific failure that pattern was originally
# observed on (malformed orchestrator tool-call syntax), but structured
# output can still fail to parse for other reasons, so the same
# resample-on-retry safeguard stays rather than assuming it's now unnecessary.
BRIEF_WRITER_RETRY_TEMPERATURE = 0.4


def _invoke_brief_writer(task_description: str) -> BriefNarrative:
    """Invoke the isolated brief_writer subagent directly, retrying with resampled temperature.

    Args:
        task_description: The full task description passed to the subagent
            as a single HumanMessage, its entire context.

    Returns:
        The subagent's structured narrative output.

    Raises:
        Exception: The last error encountered, if every attempt fails.
    """
    last_error: Exception | None = None
    for attempt in range(BRIEF_WRITER_MAX_ATTEMPTS):
        temperature = 0 if attempt == 0 else BRIEF_WRITER_RETRY_TEMPERATURE
        try:
            brief_writer = _build_brief_writer(temperature)
            result = brief_writer.invoke(
                {"messages": [HumanMessage(content=task_description)]}
            )
            return result["structured_response"]
        except Exception as exc:  # noqa: BLE001 - retry on any transient failure here
            last_error = exc
            if attempt < BRIEF_WRITER_MAX_ATTEMPTS - 1:
                time.sleep(FETCH_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error


def _fallback_opener(raw_notes: str) -> str:
    """Build a plain, code-templated opener that cannot violate the Opener Gate.

    Used when the brief_writer subagent's generated opener still fails the
    Opener Gate after a retry, relays the rep's notes verbatim instead of
    generating new text, so it can't fabricate anything.

    Args:
        raw_notes: The rep's original notes for this prospect.

    Returns:
        A generic opener referencing the notes, or a fully generic opener
        if no notes were provided.
    """
    notes = raw_notes.strip()
    if notes:
        return (
            f"Reaching out with a few things in mind: {notes} "
            "Would you be open to a quick conversation?"
        )
    return (
        "Reaching out to learn more about your business and see if "
        "there's a fit to work together."
    )
