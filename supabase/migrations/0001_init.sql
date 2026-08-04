-- ColdCallPrep initial schema
-- prospects: one row per URL a rep submits for research
-- briefs: one row per generated brief, holding the gated stated facts /
--         inferred signals separately so the fact/inference distinction
--         is preserved in storage, not just in the UI.

create extension if not exists "pgcrypto";

create table if not exists prospects (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  raw_notes text,
  created_at timestamptz not null default now()
);

create table if not exists briefs (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references prospects (id) on delete cascade,
  -- StatedFact[]: [{ category, quote }] — always direct quotes from the site
  stated_facts jsonb not null default '[]'::jsonb,
  -- InferredSignal[]: [{ signal_type, reasoning }] — only signals that
  -- passed the Opportunity Gate (non-empty signal_type + reasoning) ever
  -- land here.
  inferred_signals jsonb not null default '[]'::jsonb,
  -- The two pieces the brief_writer subagent generates, plus the
  -- assembled full-document string (see agent/tools.py::GeneratedBrief).
  company_snapshot text not null default '',
  outreach_opener text not null default '',
  brief_text text not null,
  -- false when fetch_source failed or returned near-empty content; the
  -- Source Gate requires brief_text to say so explicitly in that case.
  fetch_succeeded boolean not null,
  -- The actual Source Gate output (fetch succeeded AND content usable) —
  -- distinct from fetch_succeeded, which only reflects the HTTP result.
  source_usable boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists briefs_prospect_id_idx on briefs (prospect_id);

alter table prospects enable row level security;
alter table briefs enable row level security;

-- Single-user take-home demo: no auth, so allow full access via the anon
-- key. Tighten with real policies (e.g. scoped to auth.uid()) before this
-- ever handles real user accounts.
create policy "Allow all on prospects" on prospects
  for all using (true) with check (true);

create policy "Allow all on briefs" on briefs
  for all using (true) with check (true);
