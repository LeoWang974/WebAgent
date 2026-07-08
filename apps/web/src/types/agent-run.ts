export type AgentRunStatus =
  | "queued"
  | "running"
  | "tool_calling"
  | "rendering"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentRunStep {
  id: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  timestamp: string;
}

export interface AgentRun {
  id: string;
  sessionId: string;
  status: AgentRunStatus;
  title: string;
  progress: number;
  steps: AgentRunStep[];
  startedAt: string;
  completedAt?: string;
  error?: string;
}

export interface AgentRunEvent {
  runId: string;
  status: AgentRunStatus;
  progress: number;
  step: AgentRunStep;
  completedAt?: string;
  error?: string;
}

