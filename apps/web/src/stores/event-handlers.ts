"use client";

import {
  createPendingAssistantMessage,
  isTerminalRunStatus,
} from "./chat-store-helpers";
import { shouldSelectCreatedArtifact } from "@/lib/artifact-selection";
import type { SendMessageStreamEvent } from "@/services/adapters/types";
import type { AgentRun, AgentRunEvent, Artifact, Message, Session } from "@/types";

export interface AgentRunEventState {
  activeAgentRunId?: string;
  agentRuns: AgentRun[];
  messages: Message[];
}

export interface SendMessageStreamEventState extends AgentRunEventState {
  artifacts: Artifact[];
  selectedArtifactId?: string;
  sessions: Session[];
}

export interface SendMessageStreamEventContext {
  currentRunId: string;
  isRuntimeAdapterRun: boolean;
  modelName: string;
  requestedSkill?: string;
  sessionId: string;
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

export function applySendMessageStreamEventState(
  state: SendMessageStreamEventState,
  event: SendMessageStreamEvent,
  context: SendMessageStreamEventContext,
): Partial<SendMessageStreamEventState> {
  if (event.type === "run_started") {
    return applyStreamRunStarted(state, event);
  }
  if (event.type === "assistant_delta") {
    return applyStreamAssistantDelta(state, event, context);
  }
  if (event.type === "artifact_created") {
    return applyStreamArtifactCreated(state, event);
  }
  if (event.type === "assistant_done") {
    return applyStreamAssistantDone(state, event, context);
  }
  return {};
}

function applyStreamRunStarted(
  state: SendMessageStreamEventState,
  event: Extract<SendMessageStreamEvent, { type: "run_started" }>,
) {
  const queueLabel = queueStatusLabel(event.queueReason, event.queuePosition);
  return {
    activeAgentRunId:
      state.activeAgentRunId && state.agentRuns.some((run) => run.id === event.runId)
        ? event.runId
        : state.activeAgentRunId,
    agentRuns: state.agentRuns.map((run) =>
      run.id === event.runId
        ? {
            ...run,
            progress: event.progress,
            queueName: event.queueName,
            queuePosition: event.queuePosition,
            queueReason: event.queueReason,
            status: event.status,
          }
        : run,
    ),
    messages: queueLabel
      ? state.messages.map((message) =>
          message.sessionId === event.sessionId && message.role === "assistant" && message.isPending
            ? { ...message, pendingLabel: queueLabel }
            : message,
        )
      : state.messages,
  };
}

function queueStatusLabel(reason?: string, position?: number) {
  if (!reason && !position) {
    return "";
  }
  return position ? `${reason ?? "排队中"}，当前位置约 ${position}` : (reason ?? "排队中");
}

function applyStreamAssistantDelta(
  state: SendMessageStreamEventState,
  event: Extract<SendMessageStreamEvent, { type: "assistant_delta" }>,
  context: SendMessageStreamEventContext,
) {
  const chunk = event.content.trim();
  if (!chunk) {
    return {};
  }

  const now = new Date().toISOString();
  const currentRun = state.agentRuns.find((run) => run.id === context.currentRunId);
  const nextProgress = Math.min(90, (currentRun?.progress ?? 5) + 8);
  const existingMessageIndex = state.messages.findIndex(
    (message) => message.id === event.messageId,
  );
  const pendingIndex = state.messages.findIndex(
    (message) =>
      message.sessionId === context.sessionId &&
      message.role === "assistant" &&
      message.isPending,
  );
  const completedMessage: Message = {
    id: event.messageId,
    sessionId: context.sessionId,
    role: "assistant",
    content: chunk,
    createdAt: now,
    waitStartedAt: pendingIndex >= 0 ? state.messages[pendingIndex].waitStartedAt : undefined,
  };
  const shouldCreateNextPending = Boolean(context.isRuntimeAdapterRun || context.requestedSkill);
  const nextPendingMessage = shouldCreateNextPending
    ? createPendingAssistantMessage(
        context.sessionId,
        context.modelName,
        context.requestedSkill,
        now,
      )
    : undefined;

  const nextMessages =
    pendingIndex >= 0
      ? [
          ...state.messages.slice(0, pendingIndex),
          completedMessage,
          ...(nextPendingMessage ? [nextPendingMessage] : []),
          ...state.messages.slice(pendingIndex + 1),
        ]
      : [
          ...state.messages,
          completedMessage,
          ...(nextPendingMessage ? [nextPendingMessage] : []),
        ];

  return {
    agentRuns: state.agentRuns.map((run) =>
      run.id === context.currentRunId
        ? {
            ...run,
            hasAssistantResponse: true,
            progress: nextProgress,
            status: "running" as const,
            steps: appendAssistantStepOnce(run, event.messageId, chunk, now),
          }
        : run,
    ),
    messages:
      existingMessageIndex >= 0
        ? state.messages.map((message) =>
            message.id === event.messageId
              ? {
                  ...message,
                  content: chunk,
                  waitStartedAt:
                    message.waitStartedAt ??
                    (pendingIndex >= 0 ? state.messages[pendingIndex].waitStartedAt : undefined),
                }
              : message,
          )
        : nextMessages,
  };
}

function appendAssistantStepOnce(
  run: AgentRun,
  messageId: string,
  label: string,
  timestamp: string,
) {
  const normalizedSteps = run.steps.map((step) =>
    step.status === "running" ? { ...step, status: "completed" as const } : step,
  );
  if (normalizedSteps.some((step) => step.id === messageId)) {
    return normalizedSteps;
  }
  return [
    ...normalizedSteps,
    {
      id: messageId,
      label,
      status: "completed" as const,
      timestamp,
    },
  ];
}

function applyStreamArtifactCreated(
  state: SendMessageStreamEventState,
  event: Extract<SendMessageStreamEvent, { type: "artifact_created" }>,
) {
  const currentSelectedArtifact = state.artifacts.find(
    (artifact) => artifact.id === state.selectedArtifactId,
  );
  const targetMessage = state.messages.find((message) => message.id === event.messageId);
  const selectedBelongsToTargetMessage =
    !!state.selectedArtifactId && !!targetMessage?.artifactIds?.includes(state.selectedArtifactId);
  const artifacts = state.artifacts.some((artifact) => artifact.id === event.artifact.id)
    ? state.artifacts.map((artifact) =>
        artifact.id === event.artifact.id ? event.artifact : artifact,
      )
    : [event.artifact, ...state.artifacts];

  const shouldSelectArtifact = shouldSelectCreatedArtifact({
    currentSelectedArtifact,
    eventArtifact: event.artifact,
    selectedBelongsToTargetMessage,
  });

  return {
    artifacts,
    messages: state.messages.map((message) =>
      message.id === event.messageId
        ? {
            ...message,
            artifactIds: Array.from(new Set([...(message.artifactIds ?? []), event.artifact.id])),
          }
        : message,
    ),
    selectedArtifactId: shouldSelectArtifact ? event.artifact.id : state.selectedArtifactId,
  };
}

function applyStreamAssistantDone(
  state: SendMessageStreamEventState,
  event: Extract<SendMessageStreamEvent, { type: "assistant_done" }>,
  context: SendMessageStreamEventContext,
) {
  const completedAt = new Date().toISOString();
  const finalStatus = event.status ?? "completed";
  const existingMessage = state.messages.find((message) => message.id === event.message.id);
  const pendingIndex = state.messages.findIndex(
    (message) =>
      message.sessionId === context.sessionId &&
      message.role === "assistant" &&
      message.isPending,
  );
  let messages = state.messages.filter(
    (message) =>
      !(
        message.sessionId === context.sessionId &&
        message.role === "assistant" &&
        message.isPending
      ),
  );

  if (existingMessage) {
    messages = messages.map((message) =>
      message.id === event.message.id
        ? {
            ...event.message,
            createdAt: existingMessage.createdAt,
            waitStartedAt: existingMessage.waitStartedAt,
          }
        : message,
    );
  } else if (pendingIndex >= 0) {
    messages = [
      ...state.messages.slice(0, pendingIndex),
      {
        ...event.message,
        createdAt: completedAt,
        waitStartedAt: state.messages[pendingIndex].waitStartedAt,
      },
      ...state.messages.slice(pendingIndex + 1).filter((message) => !message.isPending),
    ];
  } else {
    messages = [...messages, event.message];
  }

  return {
    activeAgentRunId:
      state.activeAgentRunId === context.currentRunId ? undefined : state.activeAgentRunId,
    agentRuns: state.agentRuns.map((run) =>
      run.id === context.currentRunId
        ? {
            ...run,
            completedAt,
            hasAssistantResponse: true,
            progress: finalStatus === "completed" ? 100 : run.progress,
            status: finalStatus,
          }
        : run,
    ),
    messages,
    sessions: state.sessions.map((session) =>
      session.id === event.session.id ? event.session : session,
    ),
  };
}
