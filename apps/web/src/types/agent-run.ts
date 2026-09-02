/**
 * File purpose: Defines shared TypeScript contracts for agent run.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

export type AgentRunStatus =
  | "queued"
  | "running"
  | "tool_calling"
  | "rendering"
  | "completed"
  | "failed"
  | "cancelled"
  | "disconnected";

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
  hasAssistantResponse?: boolean;
  isPlainChat?: boolean;
  output?: string;
  adapterKey?: string;
  queueName?: string;
  queuePosition?: number;
  queueReason?: string;
}

export interface AgentRunEvent {
  eventId?: string;
  runId: string;
  eventType: string;
  status: AgentRunStatus;
  progress: number;
  step: AgentRunStep;
  payload?: Record<string, unknown>;
  completedAt?: string;
  error?: string;
  output?: string;
}
