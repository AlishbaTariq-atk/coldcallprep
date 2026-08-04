# ColdCallPrep

A sales rep pastes a company URL (+ optional notes). ColdCallPrep fetches
the site, quotes what the company literally says about itself, and
separately flags opportunity signals inferred from what's missing ,
never blending the two. Every claim in the output is either a direct
quote or a labeled inference with its reasoning shown alongside it.

The core discipline is enforced in code, not just prompted for:

- **Opportunity Gate** (`backend/agent/gates.py::opportunity_gate`) , an
  inferred signal only enters the brief if it has both a signal type and
  a non-empty reasoning string.
- **Source Gate** (`source_is_usable` / `enforce_source_gate`) , if the
  site fetch fails or returns near-empty content, the brief says so
  explicitly instead of inventing facts to fill the gap.
- **Opener Gate** (`opener_gate_violations`) , the outreach opener is
  checked for fabricated referrals, invented prior meetings, or a
  greeting to a name not present in the notes/facts; a violation
  triggers a retry, then a plain code-templated fallback that can't
  violate the gate.

`backend/tests/test_gates.py` proves all three with no LLM call
involved.

## Architecture

```
Next.js frontend (frontend/)  →  FastAPI backend (backend/)  →  Groq LLM
       │                              │
       │                              └─ LangGraph pipeline:
       │                                 fetch → extract → infer → generate
       │                                 (generate_brief runs as an isolated
       │                                  deepagents subagent)
       │
       └─ polls backend for live progress, renders the finished brief
```

The repo is a monorepo with two independent projects side by side:
`frontend/` (Next.js) and `backend/` (FastAPI), plus a top-level
`supabase/` directory holding the shared database schema used by the
backend.

A completed run is also written to Supabase (`prospects` + `briefs`
tables) by `backend/supabase_client.py` , one write per run, from the
backend right when the pipeline finishes.

## Prerequisites

- Node.js 18.17+ and npm
- Python 3.10+
- A [Groq](https://console.groq.com) API key (free tier; separate from
  any Claude/Anthropic account)
- A [Supabase](https://supabase.com) project (free tier)

## Setup

### 1. Clone and install the frontend

```bash
cd frontend
npm install
cp .env.example .env.local
```

`.env.local` only needs one value for local dev , the default
(`BACKEND_URL=http://localhost:8000`) already matches the backend setup
below, so you likely don't need to edit it.

### 2. Set up the backend

From the project root (open a fresh terminal, or `cd ..` back out of `frontend/` first):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and fill in:
- `GROQ_API_KEY` , from [console.groq.com](https://console.groq.com)
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` , from your Supabase
  project's **Settings → API** (use the service_role / "Secret key",
  not the anon/publishable one)

### 3. Create the Supabase tables

In your Supabase project's **SQL Editor**, run the contents of
[`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql).

### 4. Run it

One command, from `frontend/`, once the venv from step 2 exists:

```bash
cd frontend
npm run dev:all
```

This starts both the backend (`uvicorn`, auto-loading `backend/.env`,
watching `backend/` for changes) and the frontend (`next dev`) together,
with labeled/colored output. Ctrl+C once stops both , no orphaned
processes.

Prefer two separate terminals (e.g. to see backend logs on their own)?

```bash
# Terminal 1 , backend (from the project root)
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

```bash
# Terminal 2 , frontend (from the project root)
cd frontend
npm run dev
```

Open **http://localhost:3000**, click **Example** to fill in a demo
prospect with zero typing, then **Generate Brief**. The progress strip
reflects real backend steps as they happen , the "Writing brief" step
(an isolated LLM subagent call) is usually the slowest, taking up to
~30–60s.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

55 tests, all pure unit tests , no API key or network access required.
This is where the three gates are proven correct in isolation.

## Isolated tool scripts

`backend/scripts/` has three scripts for exercising individual pieces
of the pipeline against a real Groq call, each demonstrating one of the
gates live rather than just unit-testing the gate function in isolation:

```bash
cd backend && source .venv/bin/activate
GROQ_API_KEY=... python scripts/test_infer_signals.py <url>     # Opportunity Gate
GROQ_API_KEY=... python scripts/test_generate_brief.py          # Opener Gate
GROQ_API_KEY=... python scripts/test_full_pipeline.py <url> "<notes>"  # all three, end to end
```

## What's not built

- No auth , this is a single-user take-home demo. The Supabase RLS
  policies allow all access via the service-role key.
- No UI for browsing past runs , completed runs are persisted to
  Supabase but the frontend doesn't read them back or show history.
