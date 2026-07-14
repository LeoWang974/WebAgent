import type { AgentRunEvent, AgentRunStatus } from "@/types";

interface MockAgentRunOptions {
  onEvent: (event: AgentRunEvent) => void;
  runId: string;
}

const mockRunSteps: Array<{
  delayMs: number;
  label: string;
  progress: number;
  status: AgentRunStatus;
}> = [
  {
    delayMs: 250,
    label: "Queued request",
    progress: 12,
    status: "queued",
  },
  {
    delayMs: 700,
    label: "Selected skill and model",
    progress: 32,
    status: "running",
  },
  {
    delayMs: 1150,
    label: "Calling agent tools",
    progress: 58,
    status: "tool_calling",
  },
  {
    delayMs: 1600,
    label: "Preparing artifact preview",
    progress: 82,
    status: "rendering",
  },
  {
    delayMs: 2100,
    label: "Completed response",
    progress: 100,
    status: "completed",
  },
];

export function subscribeToMockAgentRun({
  onEvent,
  runId,
}: MockAgentRunOptions) {
  const timers = mockRunSteps.map((step, index) =>
    window.setTimeout(() => {
      const now = new Date().toISOString();

      onEvent({
        completedAt: step.status === "completed" ? now : undefined,
        eventType: step.status === "completed" ? "completed" : "stage_update",
        progress: step.progress,
        runId,
        status: step.status,
        step: {
          id: `${runId}_step_${index}`,
          label: step.label,
          status: step.status === "completed" ? "completed" : "running",
          timestamp: now,
        },
      });
    }, step.delayMs),
  );

  return () => {
    timers.forEach((timer) => window.clearTimeout(timer));
  };
}
