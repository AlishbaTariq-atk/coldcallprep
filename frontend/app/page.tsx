"use client";

import { AlertTriangle, ExternalLink, FileSearch } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ProgressStrip } from "@/components/progress-strip";
import { ProspectBrief } from "@/components/prospect-brief";
import { ProspectForm } from "@/components/prospect-form";
import { useRunPolling } from "@/hooks/use-run-polling";

/**
 * Main page: prospect form on the left, live progress + resulting brief on
 * the right. All state lives in useRunPolling, this component is purely
 * presentational routing of that state to the right child component.
 */
export default function Home() {
  const { status, isRunning, error, start } = useRunPolling();

  const hasStarted = status !== null;
  const result = status?.status === "done" ? status.result : null;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-5 lg:px-10">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <FileSearch className="h-4 w-4" />
            </div>
            <h1 className="text-sm font-semibold leading-none">ColdCallPrep</h1>
          </div>
          <a
            href="https://github.com/AlishbaTariq-atk/coldcallprep"
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground sm:flex"
          >
            View source
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-6 py-10 lg:px-10">
        <p className="mb-8 max-w-2xl text-base leading-relaxed text-muted-foreground">
          Every claim in a brief is either a direct quote from the
          prospect&apos;s site or a labeled inference with its reasoning
          shown next to it, enforced in code before it ever reaches you,
          not just prompted for.
        </p>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[380px_1fr]">
          <div className="lg:sticky lg:top-10 lg:self-start">
            <div className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-sm font-semibold">Research a prospect</h2>
              <p className="mb-5 text-sm font-medium text-foreground">
                Paste a company URL. We&apos;ll fetch the site, quote what
                they say, and flag gaps worth mentioning.
              </p>
              <ProspectForm onSubmit={start} isRunning={isRunning} />
            </div>
          </div>

          <div className="space-y-6">
            {!hasStarted && <EmptyState />}

            {hasStarted && <ProgressStrip status={status} />}

            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Something went wrong</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {result && <ProspectBrief result={result} />}
          </div>
        </div>
      </main>
    </div>
  );
}

/** Placeholder shown before the rep has submitted a prospect URL. */
function EmptyState() {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center rounded-lg border border-dashed text-center">
      <FileSearch className="mb-3 h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm font-medium text-foreground">No brief yet</p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
        Paste a company URL on the left and generate your first Prospect
        Brief.
      </p>
    </div>
  );
}
