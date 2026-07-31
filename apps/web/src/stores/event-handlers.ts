"use client";

import {
  createPendingAssistantMessage,
  isTerminalRunStatus,
} from "./chat-store-helpers";
import type { AgentRun, AgentRunEvent, Message } from "@/types";

export interface AgentRunEventState {
  activeAgentRunId?: string;
  agentRuns: AgentRun[];
  messages: Message[];
}

export function applyAgentRunEventState(
  state: AgentRunEventState,
  event: AgentRunEvent,
): Partial<AgentRunEventState> {
  const terminal = isTerminalRunStatus(event.status);
  const nextAgentRuns = state.agentRuns.map((run) => {
    if (run.id !== event.runId) {
      return run;
    }

    const hasExistingStep = run.steps.some((step) => step.id === event.step.id);
    const previousSteps = run.steps.map((step) => {
      if (step.id === event.step.id) {
        return event.step;
      }
      return step.status === "running"
        ? { ...step, status: "completed" as const }
        : step;
    });

    const nextRun = {
      ...run,
      completedAt: event.completedAt,
      error: event.error,
      progress: event.progress,
      status: event.status,
      steps: hasExistingStep ? previousSteps : [...previousSteps, event.step],
    };
    if (event.payload?.messageId && event.payload?.content) {
      nextRun.hasAssistantResponse = true;
    }
    return nextRun;
  });

  return {
    activeAgentRunId:
      state.activeAgentRunId === event.runId && terminal
        ? undefined
        : state.activeAgentRunId,
    agentRuns: nextAgentRuns,
    messages: terminal
      ? removePendingMessagesForRun(state, event.runId)
      : applyRunningAgentRunEventMessages(
          {
            ...state,
            agentRuns: nextAgentRuns,
          },
          event,
        ),
  };
}

function removePendingMessagesForRun(state: AgentRunEventState, runId: string) {
  return state.messages.filter(
    (message) =>
      !(
        message.role === "assistant" &&
        message.isPending &&
        state.agentRuns.some((run) => run.id === runId && run.sessionId === message.sessionId)
      ),
  );
}

function applyRunningAgentRunEventMessages(
  state: AgentRunEventState,
  event: AgentRunEvent,
) {
  const run = state.agentRuns.find((item) => item.id === event.runId);
  const content = typeof event.payload?.content === "string" ? event.payload.content.trim() : "";
  const messageId = typeof event.payload?.messageId === "string" ? event.payload.messageId : "";
  if (run && content && messageId) {
    if (state.messages.some((message) => message.id === messageId)) {
      return state.messages;
    }
    const pendingIndex = state.messages.findIndex(
      (message) =>
        message.sessionId === run.sessionId &&
        message.role === "assistant" &&
        message.isPending,
    );
    const createdAt = event.step.timestamp;
    const completedMessage: Message = {
      id: messageId,
      sessionId: run.sessionId,
      role: "assistant",
      content,
      createdAt,
      waitStartedAt:
        pendingIndex >= 0 ? state.messages[pendingIndex].waitStartedAt : run.startedAt,
    };
    const shouldKeepPending = !isTerminalRunStatus(event.status) && !run.isPlainChat;
    const nextPending = shouldKeepPending
      ? createPendingAssistantMessage(
          run.sessionId,
          run.adapterKey ?? "Agent",
          run.title === "Agent request" ? undefined : run.title,
          createdAt,
        )
      : undefined;
    if (pendingIndex >= 0) {
      return [
        ...state.messages.slice(0, pendingIndex),
        completedMessage,
        ...(nextPending ? [nextPending] : []),
        ...state.messages.slice(pendingIndex + 1),
      ];
    }
    return [...state.messages, completedMessage, ...(nextPending ? [nextPending] : [])];
  }

  return state.messages.map((message) => {
    if (message.role !== "assistant" || !message.isPending || !event.step?.label) {
      return message;
    }
    const matchingRun = state.agentRuns.find((item) => item.id === event.runId);
    if (!matchingRun || matchingRun.sessionId !== message.sessionId) {
      return message;
    }
    return {
      ...message,
      pendingLabel: event.step.label,
      waitStartedAt: message.waitStartedAt ?? matchingRun.startedAt,
    };
  });
}
