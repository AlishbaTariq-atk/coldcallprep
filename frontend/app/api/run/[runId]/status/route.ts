import { NextResponse } from "next/server";

/**
 * Proxies to the backend's /status/{run_id}, polled by the frontend to
 * drive the live progress strip. Deliberately thin, no caching, no
 * transformation, so what the UI sees is exactly what run_store.py has
 * recorded at poll time.
 */
export async function GET(
  _req: Request,
  { params }: { params: { runId: string } }
) {
  const backendUrl = process.env.BACKEND_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { error: "BACKEND_URL is not set" },
      { status: 500 }
    );
  }

  try {
    const res = await fetch(`${backendUrl}/status/${params.runId}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `backend /status failed: ${res.status} ${text}` },
        { status: res.status === 404 ? 404 : 502 }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        error:
          err instanceof Error
            ? err.message
            : "failed to reach backend /status",
      },
      { status: 502 }
    );
  }
}
