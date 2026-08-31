"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/app/lib/api-client";
import type { DataObject, RegisteredSource } from "./types";

export function useSources(baseUrl: string, token: string) {
  const [sources, setSources] = useState<RegisteredSource[]>([]);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!baseUrl || !token) return;
    const controller = new AbortController();
    apiRequest<RegisteredSource[]>(baseUrl, "/api/v1/sources", { token, signal: controller.signal })
      .then((found) => {
        setSources(found);
        setError("");
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Could not load registered sources");
      });
    return () => controller.abort();
  }, [baseUrl, token, nonce]);

  return { sources, error, refresh: () => setNonce((value) => value + 1) };
}

export function useSourceObjects(baseUrl: string, token: string, sourceId: string) {
  const [discovered, setDiscovered] = useState<{ sourceId: string; items: DataObject[] }>({ sourceId: "", items: [] });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!baseUrl || !token || !sourceId) return;
    const controller = new AbortController();
    apiRequest<DataObject[]>(baseUrl, `/api/v1/sources/${sourceId}/objects`, { token, signal: controller.signal })
      .then((found) => {
        setDiscovered({ sourceId, items: found });
        setError("");
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setDiscovered({ sourceId, items: [] });
        setError(cause instanceof Error ? cause.message : "Discovery failed");
      });
    return () => controller.abort();
  }, [baseUrl, token, sourceId]);

  const matches = Boolean(sourceId) && discovered.sourceId === sourceId;
  return { objects: matches ? discovered.items : [], error: matches ? error : "" };
}
