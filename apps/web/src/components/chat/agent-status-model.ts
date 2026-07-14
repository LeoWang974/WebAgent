import type { AgentRun } from "@/types";

const TERMINAL_STATUSES: AgentRun["status"][] = [
  "completed",
  "failed",
  "cancelled",
  "disconnected",
];

export function isAgentRunActive(run?: AgentRun) {
  return Boolean(run && !TERMINAL_STATUSES.includes(run.status));
}

export function selectAgentStatusRun(agentRuns: AgentRun[], currentSessionId: string) {
  const sessionRuns = agentRuns.filter((item) => item.sessionId === currentSessionId);
  return sessionRuns.find((item) => isAgentRunActive(item)) ?? sessionRuns[0];
}
