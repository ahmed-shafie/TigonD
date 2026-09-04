"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/app/lib/api-client";
import type { ConnectorCapability, LineageGraph, RuntimeCapability, WorkspaceSummary } from "./types";

const EMPTY_LINEAGE: LineageGraph = { nodes: [], edges: [] };

export function usePlatform(baseUrl: string, token: string) {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [lineage, setLineage] = useState<LineageGraph>(EMPTY_LINEAGE);
  const [connectors, setConnectors] = useState<ConnectorCapability[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeCapability[]>([]);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!baseUrl || !token) return;
    const controller = new AbortController();
    const options = { token, signal: controller.signal };
    Promise.all([
      apiRequest<WorkspaceSummary[]>(baseUrl, "/api/v1/platform/workspaces", options),
      apiRequest<LineageGraph>(baseUrl, "/api/v1/platform/lineage", options),
      apiRequest<ConnectorCapability[]>(baseUrl, "/api/v1/platform/connectors", options),
      apiRequest<RuntimeCapability[]>(baseUrl, "/api/v1/platform/runtimes", options),
    ])
      .then(([summaries, graph, connectorList, runtimeList]) => {
        setWorkspaces(summaries);
        setLineage(graph);
        setConnectors(connectorList);
        setRuntimes(runtimeList);
        setError("");
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Platform catalog is unavailable");
      });
    return () => controller.abort();
  }, [baseUrl, token, nonce]);

  return {
    workspaces,
    lineage,
    connectors,
    runtimes,
    error,
    cardsFor: (workspace: WorkspaceSummary["workspace"]) => workspaces.find((item) => item.workspace === workspace),
    refresh: () => setNonce((value) => value + 1),
  };
}
