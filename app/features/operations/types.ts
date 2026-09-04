export type OperationalActionKind = "deploy" | "start" | "stop" | "retry";
export type OperationalAction = {
  action_id: string;
  action: OperationalActionKind;
  deployment_id: string;
  reason: string;
  proposed_by: string;
  status: "proposed" | "approved" | "executing" | "succeeded" | "failed" | "expired" | "cancelled";
  risk_level: string;
  impact_summary: string[];
  approval_role_required: string;
  approval_expires_at: string;
  approved_by: string | null;
  result_summary: string | null;
  rollback_summary: string | null;
};
export type OperationalActionApprovalResult = { action: OperationalAction; approval_token: string | null };
export type IntelligenceMetrics = { total_feedback: number; acceptance_rate: number; successful_outcome_rate: number };
export type ProactiveInsight = {
  insight_id: string;
  severity: "info" | "warning" | "critical";
  title: string;
  evidence: string[];
  recommended_action: string;
  requires_approval: boolean;
};
