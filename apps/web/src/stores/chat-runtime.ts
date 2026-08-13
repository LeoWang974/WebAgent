import { selectPreferredArtifact } from "@/lib/artifact-selection";
import { webAgentApi } from "@/services";
import type { AgentRunUnsubscribe } from "@/services/adapters/types";
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
    if (run.sessionId === get().currentSessionId) {
      const backendMessages = await webAgentApi.listMessages(run.sessionId);
      set((state) => {
        const existingById = new Map(state.messages.map((message) => [message.id, message]));
        const currentPending = state.messages.filter(
          (message) =>
            message.sessionId === run.sessionId &&
            message.role === "assistant" &&
            message.isPending,
        );
        return {
          messages: [
            ...state.messages.filter((message) => message.sessionId !== run.sessionId),
            ...backendMessages.map((message) => ({
              ...message,
              waitStartedAt: existingById.get(message.id)?.waitStartedAt,
            })),
            ...(isTerminalRunStatus(run.status) ? [] : currentPending),
          ],
        };
      });
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
  }, 5000);
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
      void get().refreshAgentRun(runId);
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
}
