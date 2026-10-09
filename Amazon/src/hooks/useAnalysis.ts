import { useEffect, useState } from "react";
import { loadAnalysis, loadPlan, selectLocality, selectedPlanRoute, type Context } from "../api/analysis";
import type { AnalysisData, LocalityPlan } from "../types/analysis";
export default function useAnalysis(run: string, enabled: boolean) {
  const [context, setContext] = useState<Context>({run, locality: "", route: "primary"});
  const [attempt, setAttempt] = useState(0);
  const key = `${run}:${attempt}`;
  const [result, setResult] = useState<{key: string; data?: AnalysisData; error?: string}>();
  const [planResult, setPlanResult] = useState<{key: string; plan?: LocalityPlan; error?: string}>();
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    loadAnalysis(run, controller.signal).then(data => { if (!controller.signal.aborted) setResult({key, data}); })
      .catch(error => { if (!controller.signal.aborted) setResult({key, error: error.message || "Analysis unavailable"}); });
    return () => controller.abort();
  }, [run, enabled, key]);
  const current = result?.key === key ? result : undefined;
  const data = current?.data;
  const chosen = context.run === run ? context.locality : "";
  const selected = data?.planning.plans.find(plan => plan.locality.locality_id === chosen) || data?.planning.plans[0];
  const locality = selected?.locality.locality_id || "";
  const planKey = `${key}:${locality}`;
  useEffect(() => {
    if (!enabled || !selected) return;
    const controller = new AbortController();
    loadPlan(run, locality, selected, controller.signal).then(plan => { if (!controller.signal.aborted) setPlanResult({key: planKey, plan}); })
      .catch(error => { if (!controller.signal.aborted) setPlanResult({key: planKey, error: error.message || "Plan unavailable"}); });
    return () => controller.abort();
  }, [enabled, run, locality, selected, planKey]);
  const active = planResult?.key === planKey ? planResult : undefined;
  const kind = context.run === run ? context.route : "primary";
  return {data, plan: active?.plan, locality, kind, route: selectedPlanRoute(active?.plan, kind),
    loading: enabled && (!current || Boolean(selected && !active)), error: current?.error || active?.error,
    selectLocality: (id: string) => setContext(selectLocality({run, locality, route: kind}, id)),
    selectRoute: (route: "primary" | "backup") => setContext({run, locality, route}),
    retry: () => setAttempt(value => value + 1)};
}
