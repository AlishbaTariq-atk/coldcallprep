import { NextRequest, NextResponse } from "next/server";

/**
 * Kicks off a pipeline run on the FastAPI backend and hands back its
 * run_id. The frontend then polls /api/run/[runId]/status to drive the
 * live progress strip.
 */
export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { error: "BACKEND_URL is not set" },
      { status: 500 }
    );
  }

  let body: { url?: string; raw_notes?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  if (!body.url || typeof body.url !== "string") {
    return NextResponse.json({ error: "url is required" }, { status: 400 });
  }

  try {
    const res = await fetch(`${backendUrl}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: body.url,
        raw_notes: body.raw_notes ?? "",
      }),
      cache: "no-store",
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `backend /run failed: ${res.status} ${text}` },
        { status: 502 }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        error:
          err instanceof Error ? err.message : "failed to reach backend /run",
      },
      { status: 502 }
    );
  }
}
