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

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import run_store
from agent.graph import build_graph, route_after_fetch

app = FastAPI(title="ColdCallPrep backend")

# Wide open for now; tighten to the actual Vercel domain once that's fixed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Smoke-test debug endpoints (kept for future sanity checks) ------------

_debug_store: dict[str, str] = {}


class SetValueRequest(BaseModel):
    key: str
    value: str


@app.post("/debug/set")
def debug_set(body: SetValueRequest):
    _debug_store[body.key] = body.value
    return {"stored": body.key}


@app.get("/debug/get/{key}")
def debug_get(key: str):
    if key not in _debug_store:
        raise HTTPException(status_code=404, detail=f"no value stored for key '{key}'")
    return {"key": key, "value": _debug_store[key]}


# --- Real pipeline endpoints -------------------------------------------------

NODE_TO_STEP: dict[str, run_store.RunStepName] = {
    "fetch_source": "fetching_source",
    "extract_facts": "extracting_facts",
    "infer_signals": "checking_gaps",
    "generate_brief": "writing_brief",
}


class RunRequest(BaseModel):
    url: str
    raw_notes: str = ""


class RunCreatedResponse(BaseModel):
    run_id: str


@app.post("/run", response_model=RunCreatedResponse)
def start_run(body: RunRequest, background_tasks: BackgroundTasks):
    run_id = run_store.create_run()
    background_tasks.add_task(_execute_pipeline, run_id, body.url, body.raw_notes)
    return RunCreatedResponse(run_id=run_id)


@app.get("/status/{run_id}")
def get_status(run_id: str):
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
    """
    Drives run_store step-by-step as the graph ACTUALLY executes, via
    graph.stream(..., stream_mode="updates") — not a canned animation.
    Each step is marked in_progress right before the node that performs
    it starts running (predicted using the graph's own route_after_fetch,
    so this can never drift out of sync with the graph's real routing),
    and marked done the moment that node's real output arrives.
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

        run_store.complete_run(run_id, _serialize_result(url, raw_notes, final_state))
    except Exception as exc:  # noqa: BLE001 - must reach the poller, not vanish in a background task
        if pending_step:
            run_store.finish_step(run_id, pending_step, error=True)
        run_store.fail_run(run_id, str(exc))


def _serialize_result(url: str, raw_notes: str, state: dict) -> dict:
    return {
        "prospect": {"url": url, "raw_notes": raw_notes},
        "brief": {
            "stated_facts": [f.model_dump() for f in state.get("stated_facts", [])],
            "inferred_signals": [s.model_dump() for s in state.get("inferred_signals", [])],
            "brief_text": state.get("brief_text", ""),
            "fetch_succeeded": state.get("fetch_succeeded", False),
        },
    }
