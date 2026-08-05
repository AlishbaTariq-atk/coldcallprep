"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunStatus, RunStep, RunStepName } from "@/lib/types";

const STEP_ORDER: { name: RunStepName; label: string }[] = [
  { name: "fetching_source", label: "Fetching site" },
  { name: "extracting_facts", label: "Extracting facts" },
  { name: "checking_gaps", label: "Checking for gaps" },
  { name: "writing_brief", label: "Writing brief" },
];

type StepState = "pending" | "in_progress" | "done" | "error";

interface ProgressStripProps {
  status: RunStatus | null;
}

/** Format a millisecond duration as a short string, e.g. "0.4s" or "1m 12s". */
function formatDuration(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainderSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainderSeconds}s`;
}

/**
 * Elapsed time for one step: measured (finished_at - started_at) once
 * done, or live (now - started_at) while still in progress. Both are
 * real backend timestamps, this is never a synthetic/animated duration.
 */
function stepDurationMs(step: RunStep, now: number): number | null {
  const startedAt = new Date(step.started_at).getTime();
  if (step.status === "in_progress") {
    return now - startedAt;
  }
  if (step.finished_at) {
    return new Date(step.finished_at).getTime() - startedAt;
  }
  return null;
}

/**
 * Renders directly from status.steps, which only ever contains steps the
 * backend has actually recorded (see run_store.py), there is nothing
 * here on a timer faking progress. Durations shown per step are real
 * measured timestamps from the backend, not a UI animation, only the
 * "now" used for the live in-progress timer ticks locally.
 */
export function ProgressStrip({ status }: ProgressStripProps) {
  const steps = status?.steps ?? [];

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!steps.some((s) => s.status === "in_progress")) return;
    const interval = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(interval);
  }, [steps]);

  return (
    <div className="rounded-lg border bg-card px-5 py-4">
      <ol className="flex items-center">
        {STEP_ORDER.map((step, index) => {
          const recorded = steps.find((s) => s.name === step.name);
          const state: StepState = recorded?.status ?? "pending";
          const isLast = index === STEP_ORDER.length - 1;
          const durationMs = recorded ? stepDurationMs(recorded, now) : null;

          return (
            <li key={step.name} className={cn("flex items-center", !isLast && "flex-1")}>
              <div className="flex items-center gap-2">
                <StepIcon state={state} />
                <div className="flex flex-col leading-tight">
                  <span
                    className={cn(
                      "text-sm transition-colors duration-300",
                      state === "pending" && "text-muted-foreground/60",
                      state === "in_progress" && "font-medium text-primary",
                      state === "done" && "text-foreground",
                      state === "error" && "font-medium text-destructive"
                    )}
                  >
                    {step.label}
                  </span>
                  {durationMs !== null && (
                    <span className="text-xs tabular-nums text-muted-foreground/70">
                      {formatDuration(durationMs)}
                    </span>
                  )}
                </div>
              </div>
              {!isLast && (
                <div
                  className={cn(
                    "mx-3 h-px flex-1 transition-colors duration-300",
                    state === "done" ? "bg-primary/40" : "bg-border"
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Icon for a single progress-strip step, chosen by its current state. */
function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case "done":
      return <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />;
    case "in_progress":
      return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />;
    case "error":
      return <XCircle className="h-4 w-4 shrink-0 text-destructive" />;
    default:
      return <Circle className="h-4 w-4 shrink-0 text-muted-foreground/30" />;
  }
}
