"""
In-memory store for run progress, keyed by run_id. Steps are append-only
and readable mid-flight: a status GET while the run is still executing
sees whatever steps have been recorded so far, not just a final snapshot.
This is the same dict-in-a-process pattern proven live on Railway during
the deploy smoke test (main.py's /debug/set + /debug/get) — confirmed
there that state survives across separate HTTP requests on a single
instance.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

RunStepName = Literal["fetching_source", "extracting_facts", "checking_gaps", "writing_brief"]
RunStatusValue = Literal["pending", "running", "done", "error"]

STEP_LABELS: dict[RunStepName, str] = {
    "fetching_source": "Fetching site...",
    "extracting_facts": "Extracting facts...",
    "checking_gaps": "Checking for gaps...",
    "writing_brief": "Writing brief...",
}


@dataclass
class RunStep:
    name: RunStepName
    label: str
    status: Literal["in_progress", "done", "error"]
    at: str


@dataclass
class Run:
    run_id: str
    status: RunStatusValue = "pending"
    steps: list[RunStep] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None


_runs: dict[str, Run] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run() -> str:
    run_id = str(uuid.uuid4())
    with _lock:
        _runs[run_id] = Run(run_id=run_id, status="pending")
    return run_id


def start_step(run_id: str, name: RunStepName) -> None:
    """Append a new in-progress step. This is the ONLY way steps enter the
    list — there is no rewrite/replace path, so a concurrent GET always
    sees a strict prefix of what will eventually be the full list."""
    with _lock:
        run = _runs[run_id]
        run.status = "running"
        run.steps.append(
            RunStep(name=name, label=STEP_LABELS[name], status="in_progress", at=_now())
        )


def finish_step(run_id: str, name: RunStepName, *, error: bool = False) -> None:
    with _lock:
        run = _runs[run_id]
        for step in reversed(run.steps):
            if step.name == name and step.status == "in_progress":
                step.status = "error" if error else "done"
                step.at = _now()
                return


def complete_run(run_id: str, result: dict) -> None:
    with _lock:
        run = _runs[run_id]
        run.status = "done"
        run.result = result


def fail_run(run_id: str, error: str) -> None:
    with _lock:
        run = _runs[run_id]
        run.status = "error"
        run.error = error


def get_run(run_id: str) -> Optional[Run]:
    """Returns a shallow snapshot safe for a caller to serialize even while
    the background run keeps appending — we only ever hold the lock long
    enough to copy the current list, never while serializing/returning."""
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        return Run(
            run_id=run.run_id,
            status=run.status,
            steps=list(run.steps),
            result=run.result,
            error=run.error,
        )
