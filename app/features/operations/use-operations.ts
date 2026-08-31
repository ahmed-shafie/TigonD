"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/app/lib/api-client";
import type { FlowDeployment } from "@/app/features/source-intelligence/types";
import type {
  IntelligenceMetrics,
  OperationalAction,
  OperationalActionApprovalResult,
  OperationalActionKind,
  ProactiveInsight,
} from "./types";

export function useOperations(baseUrl: string, token: string) {
  const [deployments, setDeployments] = useState<FlowDeployment[]>([]);
  const [insights, setInsights] = useState<ProactiveInsight[]>([]);
  const [metrics, setMetrics] = useState<IntelligenceMetrics | null>(null);
  const [action, setAction] = useState<OperationalAction | null>(null);
  const [approvalToken, setApprovalToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!baseUrl || !token) return;
    const controller = new AbortController();
    const options = { token, signal: controller.signal };
    Promise.all([
      apiRequest<FlowDeployment[]>(baseUrl, "/api/v1/deployments", options),
      apiRequest<ProactiveInsight[]>(baseUrl, "/api/v1/intelligence/insights", options),
      apiRequest<IntelligenceMetrics>(baseUrl, "/api/v1/intelligence/metrics", options),
    ])
      .then(([flows, proactive, feedback]) => {
        setDeployments(flows);
        setInsights(proactive);
        setMetrics(feedback);
        setError("");
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Operations data is unavailable");
      });
    return () => controller.abort();
  }, [baseUrl, token, nonce]);

  const refresh = () => setNonce((value) => value + 1);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Operational action failed");
    } finally {
      setBusy(false);
    }
  };

  const propose = (deploymentId: string, kind: OperationalActionKind, reason: string) =>
    run(async () => {
      setApprovalToken("");
      const proposed = await apiRequest<OperationalAction>(baseUrl, "/api/v1/operational-actions", {
        method: "POST",
        token,
        body: { action: kind, deployment_id: deploymentId, reason },
      });
      setAction(proposed);
    });

  const decide = (decision: "approved" | "rejected") =>
    run(async () => {
      if (!action) return;
      const result = await apiRequest<OperationalActionApprovalResult>(
        baseUrl,
        `/api/v1/operational-actions/${action.action_id}/decision`,
        { method: "POST", token, body: { decision, reason: "Decided in TigonD Studio" } },
      );
      setAction(result.action);
      setApprovalToken(result.approval_token ?? "");
    });

  const execute = () =>
    run(async () => {
      if (!action || !approvalToken) return;
      const executed = await apiRequest<OperationalAction>(
        baseUrl,
        `/api/v1/operational-actions/${action.action_id}/execute`,
        { method: "POST", token, body: { approval_token: approvalToken, idempotency_key: `studio-${action.action_id}` } },
      );
      setAction(executed);
      setApprovalToken("");
      refresh();
    });

  return { deployments, insights, metrics, action, approvalToken, busy, error, propose, decide, execute, refresh };
}
