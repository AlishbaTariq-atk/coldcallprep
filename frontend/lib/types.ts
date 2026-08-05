/**
 * Shared types for the ColdCallPrep frontend. These mirror the Pydantic
 * models in /backend/agent/state.py. Persistence to Supabase happens
 * backend-side only (backend/supabase_client.py, writing the same shape
 * as RunResultBrief below), the frontend never talks to Supabase
 * directly, so there's no Database/Row type here to keep in sync.
 */

export type StatedFactCategory = "services" | "positioning" | "target_audience";

/** A direct quote pulled from the prospect's site. Never a paraphrase. */
export interface StatedFact {
  category: StatedFactCategory;
  quote: string;
}

/**
 * The backend doesn't constrain signal_type to a fixed enum, the
 * Opportunity Gate only requires it to be a non-empty string (see
 * agent/gates.py::opportunity_gate). Treat this as free text and format
 * it generically for display, not as a closed set of known values.
 */
export type SignalType = string;

/**
 * An inferred signal that has passed the Opportunity Gate: signal_type and
 * reasoning are both guaranteed non-empty by the time this shape exists.
 */
export interface InferredSignal {
  signal_type: SignalType;
  reasoning: string;
}

export type RunStepName =
  | "fetching_source"
  | "extracting_facts"
  | "checking_gaps"
  | "writing_brief";

/** One pipeline step's progress, as shown in the progress strip. */
export interface RunStep {
  name: RunStepName;
  label: string;
  status: "in_progress" | "done" | "error";
  at: string;
}

/**
 * Shape actually returned by POST /run's result. Note this has no
 * id/created_at, those exist on the Supabase rows backend/supabase_client.py
 * writes, but /run doesn't read them back, so the frontend never sees them.
 */
export interface RunResultProspect {
  url: string;
  raw_notes: string;
}

/**
 * Three-tier read on how much site content the brief is grounded in,
 * computed backend-side from the same fetch_succeeded/content-length
 * data as the Source Gate (see backend/agent/gates.py::source_status).
 */
export type SourceStatus = "Full site content retrieved" | "Partial content" | "Notes only";

export interface RunResultBrief {
  stated_facts: StatedFact[];
  inferred_signals: InferredSignal[];
  company_snapshot: string;
  outreach_opener: string;
  brief_text: string;
  fetch_succeeded: boolean;
  source_usable: boolean;
  source_status: SourceStatus;
}

/** The prospect and its generated brief, as returned once a run completes. */
export interface RunResult {
  prospect: RunResultProspect;
  brief: RunResultBrief;
}

/** Full polled state of a run: status, step-by-step progress, and the result once done. */
export interface RunStatus {
  run_id: string;
  status: "pending" | "running" | "done" | "error";
  steps: RunStep[];
  result: RunResult | null;
  error: string | null;
}
