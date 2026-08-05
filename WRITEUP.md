# ColdCallPrep, Written Note

## The problem

Cold outreach is either generic or expensive to personalize: researching a prospect properly takes
30–45 minutes per company, reading the site, figuring out what's actually worth mentioning,
drafting an opener that isn't a template. The AI tools that promise to shortcut this create a worse
problem than the one they solve: they blend what a company actually says about itself with what the
model is guessing, in the same paragraph, in the same confident tone. A rep can't tell which line is
safe to repeat on a call and which is a hallucination.

ColdCallPrep is built around one rule: never blend the two. Every claim in the output is either a
direct quote from the prospect's own site or a labeled inference with its reasoning shown alongside
it, never stated as fact without one of those two labels.

## How the harness is designed

It's a LangGraph pipeline (`fetch_source → extract_stated_facts → infer_opportunity_signals →
generate_brief`) where nothing an LLM produces is trusted until a plain Python gate checks it,
called after the model runs, before the output reaches state or the user.

- **Five sources, only one writes freely.** `fetch_source` is an HTTP fetch, no LLM involved.
  `extract_stated_facts` pulls direct quotes. `infer_opportunity_signals` proposes candidate signals
  but is deliberately ungated on its own, untrusted until the Opportunity Gate runs. `technical_signals`
  never touches an LLM at all: load time, a missing mobile viewport tag, mixed content, and broken
  links come straight from the HTTP response, in code. `generate_brief` is the only step that writes
  prose.
- **The Opportunity Gate** rejects any signal missing a type or reasoning, dedupes near-identical
  repeats, and caps the result at 5, added after one live run returned 33 candidates that were
  really just two claims repeated on a loop. A second check drops any signal that contradicts
  code-verified page evidence (a model once claimed "no social links" on a page with visible ones).
- **The Source Gate** forces an explicit "built from your notes only" disclaimer onto the brief, in
  code, whenever the fetch fails or comes back too thin, regardless of whether the model remembered
  to say so itself.
- **The Opener Gate** exists because live testing kept catching the same class of failure: a fast
  model told not to fabricate cold-outreach boilerplate does it anyway, a fake referral, an invented
  referrer's name, a backwards-direction referral, third-person drift, the rep claiming the
  prospect's own name as its own team. Each pattern is checked in code; a violation triggers one
  retry, then a plain templated fallback that can't fabricate anything.
- **`generate_brief` runs as an isolated deepagents subagent**, not another call in the shared
  pipeline. It gets a fresh message history built by the framework, a single task description in,
  nothing inherited, and the raw fetched HTML was never in its reach to begin with, so the "nothing
  is stated as fact unless it's traceable" guarantee doesn't depend on remembering to be careful
  later. An earlier version routed this through an orchestrator agent whose only job was to delegate
  to it; that hop alone accounted for ~95 of ~100 seconds per brief. Removing it kept the same
  isolation and cut latency 5–35x.
- **Model choice is a deliberate tradeoff.** Runs on Groq's `llama-3.1-8b-instant` rather than the
  70B model, which is more reliable on strict negative constraints but has a much lower free-tier
  token cap. The Opener Gate is the real backstop either way; the 70B model is one env var away if
  the cap becomes the bottleneck.

## What it does

A rep pastes a company URL and optional notes. ColdCallPrep returns a brief: the company's own
stated facts as direct quotes, opportunity signals that survived both gates (the count varies with
the site, zero is a valid, expected outcome, not a failure), and an outreach opener. Any detail
pulled only from the rep's notes is attributed to the rep's own understanding, never phrased as an
independent observation or as something the prospect said.

## How long it took

About 2-3 days  of focused, tightly scoped work.

## What I'd build next

- **A history view.** Every run is already persisted to Supabase (`prospects` + `briefs`); the
  frontend doesn't read past runs back yet.
- **CORS scoped to the real domain**, once there's a stable production frontend URL.
- **A closer look at generation latency** if the ~2-minute cases some early tests hit recur.
- **The 70B model**, if Groq's free-tier limits allow it without hurting reliability.
- **Multi-page fetching.** `fetch_source` only reads the URL it's given; crawling a small set of
  same-site links (pricing, about) would surface more of what the gates are built to catch.
