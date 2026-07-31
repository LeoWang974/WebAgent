import type { AgentRun } from "@/types";

export interface AgentRunBindingState {
  activeAgentRunId?: string;
  agentRuns: AgentRun[];
}

export function bindBackendRunId(localRunId: string, backendRunId?: string) {
  if (!backendRunId || backendRunId === localRunId) {
    return localRunId;
  }
  return backendRunId;
}

export function applyBackendRunIdBinding<T extends AgentRunBindingState>(
  state: T,
  localRunId: string,
  backendRunId: string,
): Partial<T> {
  if (backendRunId === localRunId) {
    return {};
  }

  return {
    activeAgentRunId:
      state.activeAgentRunId === localRunId ? backendRunId : state.activeAgentRunId,
    agentRuns: state.agentRuns.map((run) =>
      run.id === localRunId ? { ...run, id: backendRunId } : run,
    ),
  } as Partial<T>;
}
