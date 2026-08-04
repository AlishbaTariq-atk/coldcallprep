"""
FastAPI app for ColdCallPrep.

/run kicks off the LangGraph pipeline in a background task and returns a
run_id immediately. /status/{run_id} is polled by the frontend to drive
the live progress strip, backed by run_store.py's append-only,
mid-flight-readable step list — validated live on Railway during the
deploy smoke test before any of this real logic existed.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env by absolute path (not relative to cwd) so this works
# identically whether uvicorn is launched from /backend directly or from
# the repo root via --app-dir (as the root `npm run dev:all` script does).
load_dotenv(Path(__file__).parent / ".env")

from fastapi import BackgroundTasks, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import run_store  # noqa: E402
import supabase_client  # noqa: E402
from agent.gates import source_status  # noqa: E402
from agent.graph import build_graph, route_after_fetch  # noqa: E402

app = FastAPI(title="ColdCallPrep backend")

# Deliberately permissive for the take-home demo: this backend has no auth
# and no per-origin secrets, so an open CORS policy carries no meaningful
# risk here. Restrict `allow_origins` to the deployed frontend's domain
# before this API is ever used for anything beyond the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness check used by the deploy platform and the Railway smoke test.

    Returns:
        {"status": "ok"} if the process is up and able to serve requests.
    """
    return {"status": "ok"}


# --- Pipeline endpoints ------------------------------------------------------

NODE_TO_STEP: dict[str, run_store.RunStepName] = {
    "fetch_source": "fetching_source",
    "extract_facts": "extracting_facts",
    "infer_signals": "checking_gaps",
    "generate_brief": "writing_brief",
}


class RunRequest(BaseModel):
    """Request body for POST /run."""

    url: str
    raw_notes: str = ""


class RunCreatedResponse(BaseModel):
    """Response body for POST /run."""

    run_id: str


@app.post("/run", response_model=RunCreatedResponse)
def start_run(body: RunRequest, background_tasks: BackgroundTasks):
    """Start a pipeline run in the background and return its run_id immediately.

    Args:
        body: The prospect URL and optional rep notes.
        background_tasks: FastAPI's background task runner.

    Returns:
        RunCreatedResponse containing the new run_id, to be polled via
        GET /status/{run_id}.
    """
    run_id = run_store.create_run()
    background_tasks.add_task(_execute_pipeline, run_id, body.url, body.raw_notes)
    return RunCreatedResponse(run_id=run_id)


@app.get("/status/{run_id}")
def get_status(run_id: str):
    """Return the current progress and, once done, the result of a run.

    Args:
        run_id: The run_id returned by POST /run.

    Returns:
        A dict with run_id, status, the step list so far, and result/error
        once the run reaches a terminal state.

    Raises:
        HTTPException: 404 if no run exists for the given run_id.
    """
    run = run_store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run found for id '{run_id}'")
    return {
        "run_id": run.run_id,
        "status": run.status,
        "steps": [dataclasses.asdict(s) for s in run.steps],
        "result": run.result,
        "error": run.error,
    }


def _execute_pipeline(run_id: str, url: str, raw_notes: str) -> None:
    """Run the LangGraph pipeline in the background, driving run_store as it executes.

    Drives run_store step-by-step as the graph ACTUALLY executes, via
    graph.stream(..., stream_mode="updates") — not a canned animation. Each
    step is marked in_progress right before the node that performs it
    starts running (predicted using the graph's own route_after_fetch, so
    this can never drift out of sync with the graph's real routing), and
    marked done the moment that node's real output arrives.

    Args:
        run_id: The run_id to update as the pipeline progresses.
        url: The prospect URL to research.
        raw_notes: The rep's optional notes for this prospect.

    Returns:
        None. Writes progress and the final result/error to run_store as a
        side effect, since this runs as an untracked background task.
    """
    final_state: dict = {"url": url, "raw_notes": raw_notes}
    pending_step: run_store.RunStepName | None = None

    try:
        graph = build_graph()

        run_store.start_step(run_id, "fetching_source")
        pending_step = "fetching_source"

        for chunk in graph.stream(
            {"url": url, "raw_notes": raw_notes}, stream_mode="updates"
        ):
            for node_name, node_update in chunk.items():
                final_state.update(node_update)

                step_name = NODE_TO_STEP.get(node_name)
                if step_name and step_name == pending_step:
                    run_store.finish_step(run_id, step_name)
                    pending_step = None

                if node_name == "fetch_source":
                    next_node = route_after_fetch(final_state)
                    pending_step = NODE_TO_STEP[next_node]
                    run_store.start_step(run_id, pending_step)
                elif node_name == "extract_facts":
                    pending_step = "checking_gaps"
                    run_store.start_step(run_id, pending_step)
                elif node_name == "infer_signals":
                    pending_step = "writing_brief"
                    run_store.start_step(run_id, pending_step)

        result = _serialize_result(url, raw_notes, final_state)

        try:
            supabase_client.save_run(url, raw_notes, result["brief"])
        except Exception as exc:  # noqa: BLE001 - persistence failing must not lose the user's brief
            print(f"Supabase write failed for run {run_id}: {exc}")

        run_store.complete_run(run_id, result)
    except Exception as exc:  # noqa: BLE001 - must reach the poller, not vanish in a background task
        if pending_step:
            run_store.finish_step(run_id, pending_step, error=True)
        # Full detail server-side for debugging; only a short, non-technical
        # message reaches the frontend — a raw Groq/API exception is a wall
        # of JSON that means nothing to a rep looking at the UI.
        print(f"Pipeline run {run_id} failed: {exc}")
        run_store.fail_run(run_id, _user_facing_error(exc))


def _user_facing_error(exc: Exception) -> str:
    """Translate a pipeline exception into a short, non-technical message for the UI.

    Full exception detail is logged server-side (see _execute_pipeline); this
    is deliberately the only thing the frontend ever sees, since a raw
    Groq/API exception is a wall of JSON that means nothing to a rep.

    Args:
        exc: The exception raised somewhere in the pipeline.

    Returns:
        A short, user-facing error message.
    """
    message = str(exc)
    if "api_key" in message or "GROQ_API_KEY" in message:
        return "The AI provider isn't configured correctly on the server. Please contact the site owner."
    if "rate_limit_exceeded" in message or "code: 429" in message:
        return "The AI model is temporarily rate-limited. Please wait a few minutes and try again."
    if "tool_use_failed" in message or "Failed to call a function" in message:
        return "The AI model had trouble formatting its response. Please try again."
    if "Temporary failure in name resolution" in message or "ConnectError" in message:
        return "Couldn't reach the site or the AI provider. Please check the URL and try again."
    return "Something went wrong while generating this brief. Please try again."


def _serialize_result(url: str, raw_notes: str, state: dict) -> dict:
    """Build the JSON-serializable result shape returned by GET /status and saved to Supabase.

    Args:
        url: The prospect URL that was researched.
        raw_notes: The rep's original notes for this prospect.
        state: Final LangGraph state after the pipeline completes.

    Returns:
        A dict with `prospect` and `brief` keys, matching RunResult on the
        frontend (lib/types.ts) and the shape supabase_client.save_run expects.
    """
    return {
        "prospect": {"url": url, "raw_notes": raw_notes},
        "brief": {
            "stated_facts": [f.model_dump() for f in state.get("stated_facts", [])],
            "inferred_signals": [s.model_dump() for s in state.get("inferred_signals", [])],
            "company_snapshot": state.get("company_snapshot", ""),
            "outreach_opener": state.get("outreach_opener", ""),
            "brief_text": state.get("brief_text", ""),
            "fetch_succeeded": state.get("fetch_succeeded", False),
            "source_usable": state.get("source_usable", False),
            "source_status": source_status(
                state.get("fetch_succeeded", False), state.get("raw_content")
            ),
        },
    }
