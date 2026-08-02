"use client";

import { useCallback, useRef, useState } from "react";
import type { RunStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 1000;

interface UseRunPollingResult {
  status: RunStatus | null;
  isRunning: boolean;
  error: string | null;
  start: (url: string, rawNotes: string) => Promise<void>;
}

/**
 * Starts a run via /api/run, then polls /api/run/[runId]/status every
 * second until it reaches a terminal state. The progress strip should
 * render directly from status.steps — that list only ever contains steps
 * the backend has actually executed (see run_store.py), so there's
 * nothing here faking progress on a timer.
 */
export function useRunPolling(): UseRunPollingResult {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  const poll = useCallback(
    (runId: string) => {
      const tick = async () => {
        try {
          const res = await fetch(`/api/run/${runId}/status`, {
            cache: "no-store",
          });
          if (!res.ok) {
            throw new Error(`status check failed: ${res.status}`);
          }
          const data: RunStatus = await res.json();
          setStatus(data);

          if (data.status === "done" || data.status === "error") {
            setIsRunning(false);
            if (data.status === "error") {
              setError(data.error ?? "run failed");
            }
            return;
          }

          pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
        } catch (err) {
          setIsRunning(false);
          setError(err instanceof Error ? err.message : "polling failed");
        }
      };

      tick();
    },
    []
  );

  const start = useCallback(
    async (url: string, rawNotes: string) => {
      stopPolling();
      setError(null);
      setStatus(null);
      setIsRunning(true);

      try {
        const res = await fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, raw_notes: rawNotes }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error ?? `failed to start run: ${res.status}`);
        }

        const { run_id: runId } = await res.json();
        poll(runId);
      } catch (err) {
        setIsRunning(false);
        setError(err instanceof Error ? err.message : "failed to start run");
      }
    },
    [poll, stopPolling]
  );

  return { status, isRunning, error, start };
}
