/**
 * Shared types for the ColdCallPrep frontend. These mirror the Pydantic
 * models in /backend/agent/state.py and the Supabase schema in
 * /supabase/migrations/0001_init.sql — keep the three in sync.
 */

export type StatedFactCategory = "services" | "positioning" | "target_audience";

export interface StatedFact {
  category: StatedFactCategory;
  quote: string;
}

export type SignalType =
  | "no_booking_system"
  | "no_pricing_page"
  | "no_testimonials"
  | "dated_design"
  | "slow_load"
  | "no_blog_or_content"
  | "no_social_links"
  | "other";

/**
 * An inferred signal that has passed the Opportunity Gate: signal_type and
 * reasoning are both guaranteed non-empty by the time this shape exists.
 */
export interface InferredSignal {
  signal_type: SignalType;
  reasoning: string;
}

export interface Prospect {
  id: string;
  url: string;
  raw_notes: string | null;
  created_at: string;
}

export interface Brief {
  id: string;
  prospect_id: string;
  stated_facts: StatedFact[];
  inferred_signals: InferredSignal[];
  brief_text: string;
  fetch_succeeded: boolean;
  created_at: string;
}

export type RunStepName =
  | "fetching_source"
  | "extracting_facts"
  | "checking_gaps"
  | "writing_brief";

export interface RunStep {
  name: RunStepName;
  label: string;
  status: "in_progress" | "done" | "error";
  at: string;
}

export interface RunResult {
  prospect: Prospect;
  brief: Brief;
}

export interface RunStatus {
  run_id: string;
  status: "pending" | "running" | "done" | "error";
  steps: RunStep[];
  result: RunResult | null;
  error: string | null;
}

/** Minimal hand-maintained Supabase database type (not full codegen). */
export interface Database {
  public: {
    Tables: {
      prospects: {
        Row: Prospect;
        Insert: Omit<Prospect, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Prospect>;
      };
      briefs: {
        Row: Brief;
        Insert: Omit<Brief, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Brief>;
      };
    };
  };
}
