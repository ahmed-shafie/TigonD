"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/app/lib/api-client";
import type { SkillDefinition } from "./types";

export function useSkills(baseUrl: string, token: string) {
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  useEffect(() => {
    if (!baseUrl || !token) return;
    const controller = new AbortController();
    apiRequest<SkillDefinition[]>(baseUrl, "/api/v1/skills", { token, signal: controller.signal })
      .then(setSkills)
      .catch(() => setSkills([]));
    return () => controller.abort();
  }, [baseUrl, token]);
  return skills;
}

