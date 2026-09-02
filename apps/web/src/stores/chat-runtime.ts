/**
 * File purpose: Manages client state and actions for chat runtime.
 * Main declarations: createRequestAbortController handles create request abort controller;
 * releaseRequestAbortController handles release request abort controller; abortSessionRequest
 * handles abort session request; unsubscribeAgentRun handles unsubscribe agent run;
 * startAgentRunPolling handles start agent run polling; subscribeAgentRunEvents handles subscribe
 * agent run events; setSwitchingState handles set switching state; loadSessionWorkspace handles
 * load session workspace; resetChatRuntime handles reset chat runtime.
 */

import { selectPreferredArtifact } from "@/lib/artifact-selection";
import { webAgentApi } from "@/services";
import type { AgentRunUnsubscribe } from "@/services/adapters/types";
import type { Artifact } from "@/types";
import {
  hasPendingAssistantMessage,
  isTerminalRunStatus,
  pendingMessageForRun,
} from "./chat-store-helpers";
import type { ChatState } from "./chat-store";

export type ChatStateSetter = (
  partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>),
) => void;

const requestAbortControllers = new Map<string, AbortController>();
const agentRunUnsubscribers = new Map<string, AgentRunUnsubscribe>();
const agentRunPollers = new Map<string, number>();
const agentRunPollsInFlight = new Set<string>();
const artifactRefreshTokens = new Map<string, symbol>();
const artifactRefreshRequests = new Map<string, Promise<Artifact[]>>();

function reportArtifactRefreshError(set: ChatStateSetter, error: unknown) {
  set({
    error: error instanceof Error ? error.message : "Failed to refresh run artifacts.",
  });
}

export async function refreshRunMessages(
  get: () => ChatState,
  set: ChatStateSetter,
  sessionId: string,
) {
  const backendMessages = await webAgentApi.listMessages(sessionId);
  if (get().currentSessionId !== sessionId) {
    return;
  }
  set((state) => {
    const existingById = new Map(state.messages.map((message) => [message.id, message]));
    return {
      messages: [
        ...state.messages.filter((message) => message.sessionId !== sessionId),
        ...backendMessages.map((message) => ({
          ...message,
          waitStartedAt: existingById.get(message.id)?.waitStartedAt,
        })),
      ],
    };
  });
}

export async function refreshRunArtifacts(
  get: () => ChatState,
  set: ChatStateSetter,
  sessionId: string,
  runId: string,
) {
  const refreshKey = `${sessionId}:${runId}`;
  const token = Symbol(refreshKey);
  artifactRefreshTokens.set(refreshKey, token);
  let request = artifactRefreshRequests.get(refreshKey);
  if (!request) {
    request = webAgentApi.listArtifacts(sessionId, runId);
    artifactRefreshRequests.set(refreshKey, request);
    const clearRequest = () => {
      if (artifactRefreshRequests.get(refreshKey) === request) {
        artifactRefreshRequests.delete(refreshKey);
      }
    };
    void request.then(clearRequest, clearRequest);
  }
  const artifacts = await request;
  if (artifactRefreshTokens.get(refreshKey) !== token) {
    return;
  }
  artifactRefreshTokens.delete(refreshKey);
  set((state) => {
    const retained = state.artifacts.filter((artifact) => artifact.runId !== runId);
    const preferred = selectPreferredArtifact(artifacts, sessionId);
    return {
      artifacts: [...artifacts, ...retained],
      selectedArtifactId:
        state.currentSessionId === sessionId && preferred
          ? preferred.id
          : state.selectedArtifactId,
    };
  });
}

export function createRequestAbortController(sessionId: string) {
  requestAbortControllers.get(sessionId)?.abort();
  const controller = new AbortController();
  requestAbortControllers.set(sessionId, controller);
  return controller;
}

export function releaseRequestAbortController(
  sessionId: string,
  controller: AbortController,
) {
  if (requestAbortControllers.get(sessionId) === controller) {
    requestAbortControllers.delete(sessionId);
  }
}

export function abortSessionRequest(sessionId: string) {
  requestAbortControllers.get(sessionId)?.abort();
  requestAbortControllers.delete(sessionId);
}

export function unsubscribeAgentRun(runId: string) {
  agentRunUnsubscribers.get(runId)?.();
  agentRunUnsubscribers.delete(runId);
  const poller = agentRunPollers.get(runId);
  if (poller !== undefined) {
    window.clearInterval(poller);
    agentRunPollers.delete(runId);
  }
  agentRunPollsInFlight.delete(runId);
}

function startAgentRunPolling(
  get: () => ChatState,
  set: ChatStateSetter,
  runId: string,
) {
  if (agentRunPollers.has(runId)) {
    return;
  }

  const refresh = async () => {
    const run = await get().refreshAgentRun(runId);
    if (!run) {
      return;
    }
    if (isTerminalRunStatus(run.status) && run.sessionId === get().currentSessionId) {
      await Promise.all([
        refreshRunMessages(get, set, run.sessionId),
        refreshRunArtifacts(get, set, run.sessionId, run.id).catch((error) =>
          reportArtifactRefreshError(set, error),
        ),
      ]);
    }
    if (isTerminalRunStatus(run.status)) {
      window.setTimeout(() => unsubscribeAgentRun(run.id), 0);
      return;
    }
    const currentSessionId = get().currentSessionId;
    if (
      run.sessionId === currentSessionId &&
      !hasPendingAssistantMessage(get().messages, currentSessionId)
    ) {
      set((state) => ({
        messages: [...state.messages, pendingMessageForRun(run)],
      }));
    }
  };

  const poller = window.setInterval(() => {
    if (agentRunPollsInFlight.has(runId)) {
      return;
    }
    agentRunPollsInFlight.add(runId);
    void refresh()
      .catch((error) => {
        set({
          error: error instanceof Error ? error.message : "Failed to refresh agent run.",
        });
      })
      .finally(() => agentRunPollsInFlight.delete(runId));
  }, 10_000);
  agentRunPollers.set(runId, poller);
}

export function subscribeAgentRunEvents(
  get: () => ChatState,
  set: ChatStateSetter,
  runId: string,
) {
  if (runId.startsWith("run_")) {
    return;
  }
  if (agentRunUnsubscribers.has(runId)) {
    startAgentRunPolling(get, set, runId);
    return;
  }

  const unsubscribe = webAgentApi.subscribeAgentRun(runId, (event) => {
    get().applyAgentRunEvent(event);
    if (isTerminalRunStatus(event.status)) {
      unsubscribeAgentRun(runId);
      void get()
        .refreshAgentRun(runId)
        .then((run) =>
          run
            ? Promise.all([
                refreshRunMessages(get, set, run.sessionId),
                refreshRunArtifacts(get, set, run.sessionId, run.id),
              ]).then(() => undefined)
            : undefined,
        )
        .catch((error) => reportArtifactRefreshError(set, error));
    }
  });
  agentRunUnsubscribers.set(runId, unsubscribe);
  startAgentRunPolling(get, set, runId);
}

export function setSwitchingState(
  set: ChatStateSetter,
  get: () => ChatState,
  sessionId: string,
) {
  set({ switchingSessionId: sessionId });
  window.setTimeout(() => {
    if (get().switchingSessionId === sessionId) {
      set({ switchingSessionId: undefined });
    }
  }, 260);
}

export async function loadSessionWorkspace(
  get: () => ChatState,
  set: ChatStateSetter,
  sessionId: string,
) {
  if (!get().sessions.some((session) => session.id === sessionId)) {
    return;
  }

  try {
    const [messages, artifacts, agentRuns] = await Promise.all([
      webAgentApi.listMessages(sessionId),
      webAgentApi.listArtifacts(sessionId),
      webAgentApi.listAgentRuns(sessionId),
    ]);
    const activeRun = agentRuns.find((run) => !isTerminalRunStatus(run.status));
    const hydratedMessages =
      activeRun && !hasPendingAssistantMessage(messages, sessionId)
        ? [...messages, pendingMessageForRun(activeRun)]
        : messages;

    set((state) => ({
      activeAgentRunId:
        state.currentSessionId === sessionId ? activeRun?.id : state.activeAgentRunId,
      agentRuns: [...state.agentRuns.filter((run) => run.sessionId !== sessionId), ...agentRuns],
      artifacts: [
        ...state.artifacts.filter((artifact) => artifact.sessionId !== sessionId),
        ...artifacts,
      ],
      error: undefined,
      messages: [
        ...state.messages.filter((message) => message.sessionId !== sessionId),
        ...hydratedMessages,
      ],
      selectedArtifactId:
        state.currentSessionId === sessionId
          ? selectPreferredArtifact(artifacts, sessionId)?.id
          : state.selectedArtifactId,
      switchingSessionId:
        state.switchingSessionId === sessionId ? undefined : state.switchingSessionId,
    }));
    if (activeRun) {
      subscribeAgentRunEvents(get, set, activeRun.id);
    }
  } catch (error) {
    set((state) => ({
      error:
        state.currentSessionId === sessionId
          ? error instanceof Error
            ? error.message
            : "Failed to load conversation data."
          : state.error,
      switchingSessionId:
        state.switchingSessionId === sessionId ? undefined : state.switchingSessionId,
    }));
  }
}

export function resetChatRuntime() {
  requestAbortControllers.forEach((controller) => controller.abort());
  requestAbortControllers.clear();
  agentRunUnsubscribers.forEach((unsubscribe) => unsubscribe());
  agentRunUnsubscribers.clear();
  agentRunPollers.forEach((poller) => window.clearInterval(poller));
  agentRunPollers.clear();
  agentRunPollsInFlight.clear();
  artifactRefreshTokens.clear();
  artifactRefreshRequests.clear();
}
