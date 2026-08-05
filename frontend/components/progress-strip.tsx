"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunStatus, RunStepName } from "@/lib/types";

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

/**
 * Renders directly from status.steps, which only ever contains steps the
 * backend has actually recorded (see run_store.py), there is nothing
 * here on a timer faking progress the pipeline hasn't reached yet.
 */
export function ProgressStrip({ status }: ProgressStripProps) {
  const steps = status?.steps ?? [];

  return (
    <div className="rounded-lg border bg-card px-5 py-4">
      <ol className="flex items-center">
        {STEP_ORDER.map((step, index) => {
          const recorded = steps.find((s) => s.name === step.name);
          const state: StepState = recorded?.status ?? "pending";
          const isLast = index === STEP_ORDER.length - 1;

          return (
            <li key={step.name} className={cn("flex items-center", !isLast && "flex-1")}>
              <div className="flex items-center gap-2">
                <StepIcon state={state} />
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
