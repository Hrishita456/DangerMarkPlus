import type { FrameId, Plan, Summary, ZonesResponse } from "../types/replay";

export class ApiError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const timeout = new AbortController();
  const abort = () => timeout.abort();
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) timeout.abort();
  const timer = window.setTimeout(() => timeout.abort(), 10000);
  try {
    const response = await fetch(`${baseUrl}/api/v1${path}`, {
      signal: timeout.signal, headers: { Accept: "application/json" }, cache: "no-store",
    });
    const body = await response.json();
    if (!response.ok) {
      throw new ApiError(body.detail?.code || "API_ERROR", body.detail?.message || "Replay data could not be loaded.");
    }
    return body as T;
  } catch (error) {
    if (signal.aborted || error instanceof ApiError) throw error;
    throw new ApiError("BACKEND_UNAVAILABLE", "The replay API is unavailable. Start the backend and retry.");
  } finally {
    window.clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

function runPath(runId: string, suffix: string, frame: FrameId) {
  return `/runs/${encodeURIComponent(runId)}${suffix}?frame=${encodeURIComponent(frame)}`;
}

export const replayApi = {
  summary: (run: string, frame: FrameId, signal: AbortSignal) => get<Summary>(runPath(run, "/summary", frame), signal),
  zones: (run: string, frame: FrameId, signal: AbortSignal) => get<ZonesResponse>(runPath(run, "/zones", frame), signal),
  plan: (run: string, frame: FrameId, zone: string, signal: AbortSignal) =>
    get<Plan>(runPath(run, `/zones/${encodeURIComponent(zone)}/plan`, frame), signal),
};
