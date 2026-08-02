"""
Bare-bones FastAPI stub for the Railway smoke test.

Purpose: validate deploy plumbing (Railway hosting, cold starts, in-memory
state surviving across requests, Vercel -> Railway connectivity) BEFORE any
real agent/gate logic is built on top of it. No LangGraph, no deepagents,
no Supabase here yet — that comes after the checkpoint is verified live.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ColdCallPrep backend (smoke test stub)")

# Wide open for the smoke test; tighten to the actual Vercel domain once
# real endpoints exist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Process-local in-memory store. The real run_store.py will use this same
# pattern (dict keyed by run_id) to hold progress steps for polling — this
# stub exists specifically to prove that pattern survives across separate
# HTTP requests on Railway's hosting, not just within one process locally.
_debug_store: dict[str, str] = {}


class SetValueRequest(BaseModel):
    key: str
    value: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/debug/set")
def debug_set(body: SetValueRequest):
    _debug_store[body.key] = body.value
    return {"stored": body.key}


@app.get("/debug/get/{key}")
def debug_get(key: str):
    if key not in _debug_store:
        raise HTTPException(status_code=404, detail=f"no value stored for key '{key}'")
    return {"key": key, "value": _debug_store[key]}
