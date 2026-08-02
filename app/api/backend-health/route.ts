import { NextResponse } from "next/server";

/**
 * Smoke-test route only: proves Vercel can reach the Railway backend.
 * Superseded by /api/run once the real pipeline exists.
 */
export async function GET() {
  const backendUrl = process.env.BACKEND_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { ok: false, error: "BACKEND_URL is not set" },
      { status: 500 }
    );
  }

  const startedAt = Date.now();

  try {
    const res = await fetch(`${backendUrl}/health`, { cache: "no-store" });
    const elapsedMs = Date.now() - startedAt;
    const body = await res.json();

    return NextResponse.json({
      ok: res.ok,
      backend_status: res.status,
      backend_body: body,
      elapsed_ms: elapsedMs,
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: err instanceof Error ? err.message : "fetch to backend failed",
        elapsed_ms: Date.now() - startedAt,
      },
      { status: 502 }
    );
  }
}
