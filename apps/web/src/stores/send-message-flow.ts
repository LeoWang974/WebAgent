/**
 * File purpose: Manages client state and actions for send message flow.
 * Main declarations: mergeDiscoveredRun handles merge discovered run; sendMessageFlow handles send
 * message flow.
 */

"use client";

import { webAgentApi } from "@/services";
import type { AgentRun, Message } from "@/types";
import { applyBackendRunIdBinding, bindBackendRunId } from "./agent-run-binding";
import {
  applySendMessageStreamEventState,
  type SendMessageStreamEventState,
} from "./event-handlers";
import {
  createId,
  createPendingAssistantMessage,
  generateSessionTitle,
  isDefaultSessionTitle,
  isTerminalRunStatus,
} from "./chat-store-helpers";
import {
  createRequestAbortController,
  releaseRequestAbortController,
  refreshRunArtifacts,
  subscribeAgentRunEvents,
  type ChatStateSetter,
} from "./chat-runtime";
import type { ChatState } from "./chat-store";

type ChatStateGetter = () => ChatState;

function mergeDiscoveredRun(
  state: ChatState,
  localRunId: string,
  backendRun: AgentRun,
) {
  const boundState = {
    ...state,
    ...applyBackendRunIdBinding(state, localRunId, backendRun.id),
  };
  return {
    activeAgentRunId:
      boundState.activeAgentRunId === localRunId
        ? backendRun.id
        : boundState.activeAgentRunId,
    agentRuns: boundState.agentRuns.map((run) =>
      run.id === backendRun.id ? { ...run, ...backendRun } : run,
    ),
  };
}

export async function sendMessageFlow(
  get: ChatStateGetter,
  set: ChatStateSetter,
  content: string,
) {
  const trimmed = content.trim();
  if (!trimmed) {
    return;
  }

  const modelId = get().selectedModelId;
  const modelName = get().models.find((model) => model.id === modelId)?.name ?? "Agent";
  let sessionId = get().currentSessionId;
  if (!sessionId) {
    const session = await get().createSession();
    if (!session) {
      return;
    }
    sessionId = session.id;
  }

  const currentSession = get().sessions.find((session) => session.id === sessionId);
  const shouldAutoRename = Boolean(
    currentSession && isDefaultSessionTitle(currentSession.title),
  );
  const autoTitle = generateSessionTitle(trimmed);
  const now = new Date().toISOString();
  const localRunId = createId("run");
  let currentRunId = localRunId;
  const optimisticUserMessage: Message = {
    id: createId("message_user"),
    sessionId,
    role: "user",
    content: trimmed,
    createdAt: now,
  };
  const pendingAssistantMessage = createPendingAssistantMessage(
    sessionId,
    modelName,
    undefined,
  );
  const run: AgentRun = {
    id: localRunId,
    hasAssistantResponse: false,
    isPlainChat: false,
    progress: 0,
    sessionId,
    startedAt: now,
    status: "running",
    steps: [],
    title: "Hermes request",
  };
  const requestAbortController = createRequestAbortController(sessionId);

  set((state) => ({
    activeAgentRunId: localRunId,
    agentRuns: [run, ...state.agentRuns],
    error: undefined,
    messages: [...state.messages, optimisticUserMessage, pendingAssistantMessage],
    sessions: state.sessions.map((session) =>
      session.id === sessionId
        ? {
            ...session,
            status: "running",
            title: shouldAutoRename ? autoTitle : session.title,
            updatedAt: now,
          }
        : session,
    ),
  }));

  if (shouldAutoRename) {
    void webAgentApi
      .updateSession(sessionId, { title: autoTitle })
      .then((session) => {
        set((state) => ({
          sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
        }));
      })
      .catch((error) => {
        set({ error: error instanceof Error ? error.message : "Failed to rename session." });
      });
  }

  let discoveryTimeout: number | undefined = window.setTimeout(() => {
    discoveryTimeout = undefined;
    if (currentRunId !== localRunId) {
      return;
    }
    void webAgentApi
      .listAgentRuns(sessionId)
      .then((runs) => {
        const startedAtMs = Date.parse(now);
        const backendRun = runs.find(
          (candidate) =>
            !candidate.id.startsWith("run_") &&
            candidate.sessionId === sessionId &&
            !isTerminalRunStatus(candidate.status) &&
            Date.parse(candidate.startedAt) >= startedAtMs - 10_000,
        );
        if (!backendRun || currentRunId !== localRunId) {
          return;
        }
        currentRunId = backendRun.id;
        set((state) => mergeDiscoveredRun(state, localRunId, backendRun));
        subscribeAgentRunEvents(get, set, backendRun.id);
      })
      .catch(() => {
        // The streaming request remains the owner of visible error reporting.
      });
  }, 3000);

  const stopDiscovery = () => {
    if (discoveryTimeout !== undefined) {
      window.clearTimeout(discoveryTimeout);
      discoveryTimeout = undefined;
    }
  };

  try {
    await webAgentApi.sendMessageStream(
      {
        content: trimmed,
        modelId,
        signal: requestAbortController.signal,
        sessionId,
      },
      (event) => {
        const previousRunId = currentRunId;
        currentRunId = bindBackendRunId(
          currentRunId,
          "runId" in event ? event.runId : undefined,
        );
        if (event.type === "run_started") {
          stopDiscovery();
        }
        set((state) => {
          const boundState: SendMessageStreamEventState = {
            ...state,
            ...applyBackendRunIdBinding(state, previousRunId, currentRunId),
          };
          return applySendMessageStreamEventState(boundState, event, {
            currentRunId,
            modelName,
            sessionId,
          });
        });
      },
    );
    if (!currentRunId.startsWith("run_")) {
      const refreshedRun = await webAgentApi.getAgentRun(currentRunId);
      set((state) => ({
        activeAgentRunId: isTerminalRunStatus(refreshedRun.status)
          ? undefined
          : state.activeAgentRunId,
        agentRuns: state.agentRuns.map((runItem) =>
          runItem.id === refreshedRun.id ? refreshedRun : runItem,
        ),
      }));
      if (isTerminalRunStatus(refreshedRun.status)) {
        try {
          await refreshRunArtifacts(get, set, sessionId, refreshedRun.id);
        } catch (error) {
          set({
            error:
              error instanceof Error ? error.message : "Failed to refresh run artifacts.",
          });
        }
      }
    }
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    if (!aborted && !currentRunId.startsWith("run_")) {
      try {
        const backendRun = await webAgentApi.getAgentRun(currentRunId);
        if (!isTerminalRunStatus(backendRun.status)) {
          set((state) => mergeDiscoveredRun(state, localRunId, backendRun));
          subscribeAgentRunEvents(get, set, backendRun.id);
          return;
        }
      } catch {
        // Fall through to the visible request failure state.
      }
    }
    set((state) => ({
      activeAgentRunId: undefined,
      agentRuns: state.agentRuns.map((runItem) =>
        runItem.id === currentRunId
          ? {
              ...runItem,
              completedAt: new Date().toISOString(),
              error: aborted
                ? undefined
                : error instanceof Error
                  ? error.message
                  : "Failed to send message.",
              status: aborted ? "cancelled" : "failed",
            }
          : runItem,
      ),
      error: aborted
        ? undefined
        : error instanceof Error
          ? error.message
          : "Failed to send message.",
      messages: state.messages.filter(
        (message) =>
          !(
            message.sessionId === sessionId &&
            message.role === "assistant" &&
            message.isPending
          ),
      ),
    }));
  } finally {
    stopDiscovery();
    releaseRequestAbortController(sessionId, requestAbortController);
  }
}
