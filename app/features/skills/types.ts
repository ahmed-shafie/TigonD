export type SkillDefinition = {
  key: string;
  name: string;
  description: string;
  category: string;
  version: string;
  risk_level: "low" | "medium" | "high";
  allowed_roles: string[];
  requires_approval: boolean;
  implemented: boolean;
  enabled: boolean;
};

