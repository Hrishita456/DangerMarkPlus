import { useEffect, useState } from "react";
import { ApiError, replayApi } from "../api/client";
import type { FrameId, ReplayData, RouteKind } from "../types/replay";

const frames: FrameId[] = ["evacuate", "prepare", "monitor", "clear"];

export default function useReplay(enabled = true) {
  const [initial] = useState(() => new URLSearchParams(window.location.search));
  const [runId] = useState("demo-yamuna-2023");
  const [frameId, setFrameId] = useState<FrameId>(() => {
    const frame = initial.get("frame") as FrameId;
    return frames.includes(frame) ? frame : "evacuate";
  });
  const [selectedZone, setSelectedZone] = useState(initial.get("zone") || "07");
  const [selectedRoute, setSelectedRoute] = useState<RouteKind>(initial.get("route") === "backup" ? "backup" : "primary");
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: ReplayData; error?: ApiError }>();
  const requestKey = `${runId}:${frameId}:${selectedZone}:${attempt}`;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    Promise.all([
      replayApi.summary(runId, frameId, controller.signal),
      replayApi.zones(runId, frameId, controller.signal),
      replayApi.plan(runId, frameId, selectedZone, controller.signal),
    ]).then(([summary, response, plan]) => {
      if (controller.signal.aborted) return;
      // Never combine responses from different fixture revisions or snapshots.
      if ([response, plan].some(item => item.run_id !== summary.run_id || item.revision !== summary.revision
        || item.replay_at !== summary.replay_at || item.frame_id !== summary.frame_id)
        || plan.zone.id !== selectedZone || !response.zones.some(zone => zone.id === selectedZone)) {
        throw new ApiError("INCONSISTENT_REPLAY", "The replay changed while loading. Retry to load one consistent snapshot.");
      }
      setResult({ key: requestKey, data: { summary, zones: response.zones, plan } });
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ key: requestKey, error: error instanceof ApiError
        ? error : new ApiError("INVALID_REPLAY", "The API returned an invalid replay response.") });
    });
    return () => controller.abort();
  }, [enabled, runId, frameId, selectedZone, requestKey]);

  const current = result?.key === requestKey ? result : undefined;
  const data = current?.data;
  const route = selectedRoute === "backup" ? data?.plan.backup_route : data?.plan.primary_route;
  const planUnavailable = Boolean(data && !route);
  const error = current?.error || (planUnavailable ? new ApiError("PLAN_UNAVAILABLE", "This zone has no backup plan. Select its primary route.") : undefined);

  return {
    runId, frameId, replayAt: data?.summary.replay_at, selectedZone, selectedRoute,
    setFrameId, setSelectedZone, setSelectedRoute, data, route,
    loading: !current, error, retry: () => setAttempt(value => value + 1),
    reset: () => { setSelectedZone("07"); setSelectedRoute("primary"); setFrameId("evacuate"); setAttempt(value => value + 1); },
  };
}
