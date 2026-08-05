"""
In-memory store for run progress, keyed by run_id. Steps are append-only
and readable mid-flight: a status GET while the run is still executing
sees whatever steps have been recorded so far, not just a final snapshot.
This is the same dict-in-a-process pattern validated live on Railway
during the initial deploy smoke test, which confirmed state survives
across separate HTTP requests on a single instance before any of this
real pipeline logic existed.
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
    """A single pipeline step's progress, as shown in the frontend's progress strip."""

    name: RunStepName
    label: str
    status: Literal["in_progress", "done", "error"]
    at: str


@dataclass
class Run:
    """The full state of one pipeline run: its steps so far, and its result once done."""

    run_id: str
    status: RunStatusValue = "pending"
    steps: list[RunStep] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None


_runs: dict[str, Run] = {}
_lock = threading.Lock()


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def create_run() -> str:
    """Create a new run with a fresh run_id and pending status.

    Returns:
        The new run's run_id.
    """
    run_id = str(uuid.uuid4())
    with _lock:
        _runs[run_id] = Run(run_id=run_id, status="pending")
    return run_id


def start_step(run_id: str, name: RunStepName) -> None:
    """Append a new in-progress step and mark the run as running.

    This is the ONLY way steps enter the list, there is no rewrite/replace
    path, so a concurrent GET always sees a strict prefix of what will
    eventually be the full list.

    Args:
        run_id: The run to update.
        name: The step that is starting.
    """
    with _lock:
        run = _runs[run_id]
        run.status = "running"
        run.steps.append(
            RunStep(name=name, label=STEP_LABELS[name], status="in_progress", at=_now())
        )


def finish_step(run_id: str, name: RunStepName, *, error: bool = False) -> None:
    """Mark the most recent in-progress step with the given name as done or errored.

    Args:
        run_id: The run to update.
        name: The step to finish.
        error: If True, mark the step as errored instead of done.
    """
    with _lock:
        run = _runs[run_id]
        for step in reversed(run.steps):
            if step.name == name and step.status == "in_progress":
                step.status = "error" if error else "done"
                step.at = _now()
                return


def complete_run(run_id: str, result: dict) -> None:
    """Mark a run as done and attach its final result.

    Args:
        run_id: The run to update.
        result: The serialized pipeline result (see main.py::_serialize_result).
    """
    with _lock:
        run = _runs[run_id]
        run.status = "done"
        run.result = result


def fail_run(run_id: str, error: str) -> None:
    """Mark a run as errored with a user-facing error message.

    Args:
        run_id: The run to update.
        error: A short, user-facing error message (see main.py::_user_facing_error).
    """
    with _lock:
        run = _runs[run_id]
        run.status = "error"
        run.error = error


def get_run(run_id: str) -> Optional[Run]:
    """Fetch a snapshot of a run's current state.

    Returns a shallow snapshot safe for a caller to serialize even while
    the background run keeps appending, we only ever hold the lock long
    enough to copy the current list, never while serializing/returning.

    Args:
        run_id: The run to fetch.

    Returns:
        A copy of the run's current state, or None if no run exists for
        that run_id.
    """
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
