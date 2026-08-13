"use client";

import { create } from "zustand";
import { selectPreferredArtifact } from "@/lib/artifact-selection";
import { settingsApi, webAgentApi } from "@/services";
import { ApiError } from "@/services/api-client";
import type { AgentRunUnsubscribe } from "@/services/adapters/types";
import { applyBackendRunIdBinding, bindBackendRunId } from "./agent-run-binding";
import { applyAgentRunEventState, applySendMessageStreamEventState } from "./event-handlers";
import {
  createId,
  createPendingAssistantMessage,
  generateSessionTitle,
  hasPendingAssistantMessage,
  isDefaultSessionTitle,
  isTerminalRunStatus,
  pendingMessageForRun,
} from "./chat-store-helpers";
import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  Message,
  ModelConfig,
  ConversationFolder,
  Session,
  Skill,
  SkillKey,
} from "@/types";

interface ChatState {
  activeAgentRunId?: string;
  agentRuns: AgentRun[];
  artifacts: Artifact[];
  currentSessionId: string;
  error?: string;
  folders: ConversationFolder[];
  hydrated: boolean;
  loading: boolean;
  messages: Message[];
  models: ModelConfig[];
  selectedArtifactId?: string;
  selectedModelId?: string;
  sharingSessionId?: string;
  sessions: Session[];
  skills: Skill[];
  switchingSessionId?: string;
  runtimeStatusCheckedAt?: string;
  runtimeStatusRefreshing: boolean;
  testingModelId?: string;
  updatingSkillKey?: SkillKey;
  addModel: (input: Omit<ModelConfig, "id" | "isDefault" | "isAvailable">) => Promise<void>;
  applyAgentRunEvent: (event: AgentRunEvent) => void;
  createConversationFolder: (name: string) => Promise<void>;
  createSession: () => Promise<Session | undefined>;
  deleteArtifact: (artifactId: string) => Promise<void>;
  deleteConversationFolder: (folderId: string) => Promise<void>;
  deleteModel: (modelId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<boolean>;
  ensureArtifactLoaded: (artifactId: string) => Promise<void>;
  hydrate: () => Promise<void>;
  refreshArtifacts: () => Promise<void>;
  resetWorkspace: () => void;
  retryHydrate: () => Promise<void>;
  refreshRuntimeModelStatus: () => Promise<void>;
  refreshAgentRun: (runId: string) => Promise<AgentRun | undefined>;
  moveSessionToFolder: (sessionId: string, folderId?: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectModel: (modelId: string) => void;
  selectSession: (sessionId: string) => void;
  setSessionVisibility: (sessionId: string, visibility: Session["visibility"]) => Promise<void>;
  shareSession: (sessionId: string, email: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  setDefaultModel: (modelId: string) => Promise<void>;
  setDefaultSkill: (skillKey: SkillKey) => Promise<void>;
  stopActiveRun: (runId?: string) => void;
  testModelConnection: (modelId: string) => Promise<void>;
  toggleSessionPinned: (sessionId: string) => Promise<void>;
  toggleSkillEnabled: (skillKey: SkillKey) => Promise<void>;
  unshareSession: (sessionId: string, userId: string) => Promise<void>;
  updateModel: (modelId: string, input: Partial<ModelConfig>) => Promise<void>;
  updateSkillVersion: (skillKey: SkillKey, direction: "update" | "rollback") => Promise<void>;
}

const requestAbortControllers = new Map<string, AbortController>();
const agentRunUnsubscribers = new Map<string, AgentRunUnsubscribe>();

const agentRunPollers = new Map<string, number>();
const agentRunPollsInFlight = new Set<string>();

function unsubscribeAgentRun(runId: string) {
  agentRunUnsubscribers.get(runId)?.();
  agentRunUnsubscribers.delete(runId);
  const poller = agentRunPollers.get(runId);
  if (poller !== undefined) {
    window.clearInterval(poller);
    agentRunPollers.delete(runId);
  }
}

function startAgentRunPolling(
  get: () => ChatState,
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
      useChatStore.setState((state) => {
        const existingById = new Map(state.messages.map((message) => [message.id, message]));
        const currentPending = state.messages.filter(
          (message) =>
            message.sessionId === run.sessionId &&
            message.role === "assistant" &&
            message.isPending,
        );
        const pendingMessages = isTerminalRunStatus(run.status) ? [] : currentPending;
        return {
          messages: [
            ...state.messages.filter((message) => message.sessionId !== run.sessionId),
            ...backendMessages.map((message) => ({
              ...message,
              waitStartedAt: existingById.get(message.id)?.waitStartedAt,
            })),
            ...pendingMessages,
          ],
        };
      });
    }
    if (isTerminalRunStatus(run.status)) {
      setTimeout(() => unsubscribeAgentRun(run.id), 0);
      return;
    }
    const currentSessionId = get().currentSessionId;
    if (
      run.sessionId === currentSessionId &&
      !hasPendingAssistantMessage(get().messages, currentSessionId)
    ) {
      useChatStore.setState((state) => ({
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
        useChatStore.setState({
          error: error instanceof Error ? error.message : "Failed to refresh agent run.",
        });
      })
      .finally(() => agentRunPollsInFlight.delete(runId));
  }, 5000);
  agentRunPollers.set(runId, poller);
}

function subscribeAgentRunEvents(
  get: () => ChatState,
  runId: string,
) {
  if (runId.startsWith("run_")) {
    return;
  }
  if (agentRunUnsubscribers.has(runId)) {
    startAgentRunPolling(get, runId);
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
  startAgentRunPolling(get, runId);
}

function setSwitchingState(
  set: (partial: Partial<ChatState>) => void,
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

async function loadSessionWorkspace(get: () => ChatState, sessionId: string) {
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

    useChatStore.setState((state) => ({
      activeAgentRunId:
        state.currentSessionId === sessionId ? activeRun?.id : state.activeAgentRunId,
      agentRuns: [
        ...state.agentRuns.filter((run) => run.sessionId !== sessionId),
        ...agentRuns,
      ],
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
      subscribeAgentRunEvents(get, activeRun.id);
    }
  } catch (error) {
    useChatStore.setState((state) => ({
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

export const useChatStore = create<ChatState>((set, get) => ({
  activeAgentRunId: undefined,
  agentRuns: [],
  artifacts: [],
  currentSessionId: "",
  error: undefined,
  folders: [],
  hydrated: false,
  loading: false,
  messages: [],
  models: [],
  runtimeStatusCheckedAt: undefined,
  runtimeStatusRefreshing: false,
  selectedArtifactId: undefined,
  selectedModelId: undefined,
  sharingSessionId: undefined,
  sessions: [],
  skills: [],
  switchingSessionId: undefined,
  testingModelId: undefined,
  updatingSkillKey: undefined,
  applyAgentRunEvent: (event) => {
    set((state) => applyAgentRunEventState(state, event));
  },
  addModel: async (input) => {
    set({ error: undefined });
    try {
      const model = await settingsApi.addModel(input);
      set((state) => ({
        models: [...state.models, model],
        selectedModelId: state.selectedModelId ?? model.id,
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to add model." });
    }
  },
  createSession: async () => {
    set({ error: undefined });
    try {
      const session = await webAgentApi.createSession({});
      set((state) => ({
        currentSessionId: session.id,
        selectedArtifactId: undefined,
        sessions: [session, ...state.sessions],
      }));
      setSwitchingState(set, get, session.id);
      return session;
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to create session." });
      return undefined;
    }
  },
  createConversationFolder: async (name) => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      return;
    }
    try {
      const folder = await webAgentApi.createConversationFolder(trimmedName);
      set((state) => ({ folders: [...state.folders, folder] }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to create folder." });
    }
  },
  deleteArtifact: async (artifactId) => {
    try {
      await webAgentApi.deleteArtifact(artifactId);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to delete artifact." });
      return;
    }

    set((state) => {
      const artifacts = state.artifacts.filter((artifact) => artifact.id !== artifactId);
      const selectedArtifactId =
        state.selectedArtifactId === artifactId
          ? artifacts.find((artifact) => artifact.sessionId === state.currentSessionId)?.id
          : state.selectedArtifactId;

      return {
        artifacts,
        messages: state.messages.map((message) => ({
          ...message,
          artifactIds: message.artifactIds?.filter((id) => id !== artifactId),
        })),
        selectedArtifactId,
      };
    });
  },
  deleteModel: async (modelId) => {
    try {
      await settingsApi.deleteModel(modelId);
      set((state) => {
        const models = state.models.filter((item) => item.id !== modelId);
        const selectedModelId =
          state.selectedModelId === modelId
            ? models.find((item) => item.isDefault)?.id ?? models[0]?.id
            : state.selectedModelId;

        return { models, selectedModelId };
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to delete model." });
    }
  },
  deleteSession: async (sessionId) => {
    try {
      await webAgentApi.deleteSession(sessionId);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to delete session." });
      return false;
    }

    set((state) => {
      const sessions = state.sessions.filter((session) => session.id !== sessionId);
      const currentSessionId =
        state.currentSessionId === sessionId ? sessions[0]?.id ?? "" : state.currentSessionId;
      const selectedArtifactId =
        state.currentSessionId === sessionId
          ? state.artifacts.find((artifact) => artifact.sessionId === currentSessionId)?.id
          : state.selectedArtifactId;

      return {
        activeAgentRunId:
          state.agentRuns.find((run) => run.id === state.activeAgentRunId)?.sessionId ===
          sessionId
            ? undefined
            : state.activeAgentRunId,
        agentRuns: state.agentRuns.filter((run) => run.sessionId !== sessionId),
        artifacts: state.artifacts.filter((artifact) => artifact.sessionId !== sessionId),
        currentSessionId,
        messages: state.messages.filter((message) => message.sessionId !== sessionId),
        selectedArtifactId,
        sessions,
        switchingSessionId: state.switchingSessionId === sessionId ? undefined : state.switchingSessionId,
      };
    });
    return true;
  },
  deleteConversationFolder: async (folderId) => {
    try {
      await webAgentApi.deleteConversationFolder(folderId);
      set((state) => ({
        folders: state.folders.filter((folder) => folder.id !== folderId),
        sessions: state.sessions.map((session) =>
          session.folderId === folderId ? { ...session, folderId: undefined } : session,
        ),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to delete folder." });
    }
  },
  hydrate: async () => {
    if (get().hydrated || get().loading) {
      return;
    }

    set({ error: undefined, loading: true });
    try {
      const [sessions, skills, models, folders] = await Promise.all([
        webAgentApi.listSessions(),
        webAgentApi.listSkills(),
        webAgentApi.listModels(),
        webAgentApi.listConversationFolders(),
      ]);
      const preferredSessionId = get().currentSessionId;
      const currentSessionId = sessions.some((session) => session.id === preferredSessionId)
        ? preferredSessionId
        : sessions[0]?.id ?? "";
      const modelConfigs = models;
      const selectedModelId =
        modelConfigs.find((model) => model.isDefault)?.id ??
        modelConfigs[0]?.id ??
        models.find((model) => model.isDefault)?.id ??
        models[0]?.id;
      set({
        artifacts: [],
        activeAgentRunId: undefined,
        agentRuns: [],
        currentSessionId,
        folders,
        hydrated: true,
        loading: false,
        messages: [],
        models,
        selectedArtifactId: undefined,
        selectedModelId,
        sessions,
        skills,
      });
      if (currentSessionId) {
        await loadSessionWorkspace(get, currentSessionId);
      }
      void get().refreshRuntimeModelStatus();
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to load workspace data.",
        hydrated: true,
        loading: false,
      });
    }
  },
  retryHydrate: async () => {
    set({ hydrated: false, loading: false });
    await get().hydrate();
  },
  refreshArtifacts: async () => {
    const sessionId = get().currentSessionId;
    if (!sessionId) {
      return;
    }
    try {
      const artifacts = await webAgentApi.listArtifacts(sessionId);
      const selectedArtifactId = artifacts.some((artifact) => artifact.id === get().selectedArtifactId)
        ? get().selectedArtifactId
        : selectPreferredArtifact(artifacts, sessionId)?.id;
      set((state) => ({
        artifacts: [
          ...state.artifacts.filter((artifact) => artifact.sessionId !== sessionId),
          ...artifacts,
        ],
        selectedArtifactId,
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to refresh artifacts." });
    }
  },
  resetWorkspace: () => {
    requestAbortControllers.forEach((controller) => controller.abort());
    requestAbortControllers.clear();
    agentRunUnsubscribers.forEach((unsubscribe) => unsubscribe());
    agentRunUnsubscribers.clear();
    agentRunPollers.forEach((poller) => window.clearInterval(poller));
    agentRunPollers.clear();
    agentRunPollsInFlight.clear();

    set({
      activeAgentRunId: undefined,
      agentRuns: [],
      artifacts: [],
      currentSessionId: "",
      error: undefined,
      folders: [],
      hydrated: false,
      loading: false,
      messages: [],
      models: [],
      runtimeStatusCheckedAt: undefined,
      runtimeStatusRefreshing: false,
      selectedArtifactId: undefined,
      selectedModelId: undefined,
      sharingSessionId: undefined,
      sessions: [],
      skills: [],
      switchingSessionId: undefined,
      testingModelId: undefined,
      updatingSkillKey: undefined,
    });
  },
  refreshAgentRun: async (runId) => {
    if (runId.startsWith("run_")) {
      unsubscribeAgentRun(runId);
      set((state) => ({
        activeAgentRunId:
          state.activeAgentRunId === runId ? undefined : state.activeAgentRunId,
        agentRuns: state.agentRuns.filter((run) => run.id !== runId),
      }));
      return undefined;
    }
    try {
      const run = await webAgentApi.getAgentRun(runId);
      const terminal = isTerminalRunStatus(run.status);
      set((state) => ({
        activeAgentRunId:
          state.activeAgentRunId === run.id && terminal ? undefined : state.activeAgentRunId,
        agentRuns: state.agentRuns.some((item) => item.id === run.id)
          ? state.agentRuns.map((item) => (item.id === run.id ? run : item))
          : [run, ...state.agentRuns],
      }));
      if (terminal) {
        unsubscribeAgentRun(run.id);
      }
      return run;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        unsubscribeAgentRun(runId);
        set((state) => ({
          activeAgentRunId:
            state.activeAgentRunId === runId ? undefined : state.activeAgentRunId,
          agentRuns: state.agentRuns.filter((run) => run.id !== runId),
          messages: state.messages.filter(
            (message) =>
              !(
                message.isPending &&
                state.agentRuns.some(
                  (run) => run.id === runId && run.sessionId === message.sessionId,
                )
              ),
          ),
        }));
        return undefined;
      }
      set({ error: error instanceof Error ? error.message : "Failed to load run details." });
      return undefined;
    }
  },
  renameSession: async (sessionId, title) => {
    const nextTitle = title.trim();
    if (!nextTitle) {
      return;
    }

    const previousSession = get().sessions.find((session) => session.id === sessionId);
    if (previousSession?.title === nextTitle) {
      return;
    }

    const now = new Date().toISOString();
    set((state) => ({
      error: undefined,
      sessions: state.sessions.map((session) =>
        session.id === sessionId
          ? { ...session, title: nextTitle, updatedAt: now }
          : session,
      ),
    }));

    try {
      const session = await webAgentApi.updateSession(sessionId, { title: nextTitle });
      set((state) => ({
        sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
      }));
    } catch (error) {
      set((state) => ({
        error: error instanceof Error ? error.message : "Failed to rename session.",
        sessions: previousSession
          ? state.sessions.map((session) =>
              session.id === sessionId ? previousSession : session,
            )
          : state.sessions,
      }));
    }
  },
  moveSessionToFolder: async (sessionId, folderId) => {
    const previousSession = get().sessions.find((session) => session.id === sessionId);
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === sessionId ? { ...session, folderId } : session,
      ),
    }));
    try {
      const session = await webAgentApi.updateSession(sessionId, {
        folderId: folderId ?? null,
      });
      set((state) => ({
        sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
      }));
    } catch (error) {
      set((state) => ({
        error: error instanceof Error ? error.message : "Failed to move session.",
        sessions: previousSession
          ? state.sessions.map((session) =>
              session.id === sessionId ? previousSession : session,
            )
          : state.sessions,
      }));
    }
  },
  ensureArtifactLoaded: async (artifactId) => {
    const artifact = get().artifacts.find((item) => item.id === artifactId);
    const hasPreviewPayload =
      !!artifact?.content ||
      !!(artifact?.metadata?.images as unknown[] | undefined)?.length ||
      !!(artifact?.metadata?.rows as unknown[] | undefined)?.length ||
      !!(artifact?.metadata?.slides as unknown[] | undefined)?.length;
    if (!artifact || hasPreviewPayload) {
      return;
    }

    try {
      const detailedArtifact = await webAgentApi.getArtifact(artifactId);
      set((state) => ({
        artifacts: state.artifacts.map((item) =>
          item.id === artifactId ? { ...item, ...detailedArtifact } : item,
        ),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to load artifact." });
    }
  },
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId }),
  selectModel: (modelId) => set({ selectedModelId: modelId }),
  selectSession: (sessionId) => {
    const artifact = selectPreferredArtifact(get().artifacts, sessionId);
    const activeRun = get().agentRuns.find(
      (run) => run.sessionId === sessionId && !isTerminalRunStatus(run.status),
    );
    set({
      activeAgentRunId: activeRun?.id,
      currentSessionId: sessionId,
      messages:
        activeRun && !hasPendingAssistantMessage(get().messages, sessionId)
          ? [...get().messages, pendingMessageForRun(activeRun)]
          : get().messages,
      selectedArtifactId: artifact?.id,
    });
    if (activeRun) {
      subscribeAgentRunEvents(get, activeRun.id);
    }
    setSwitchingState(set, get, sessionId);
    void loadSessionWorkspace(get, sessionId);
  },
  setSessionVisibility: async (sessionId, visibility) => {
    if (!visibility) {
      return;
    }

    set({ sharingSessionId: sessionId });
    try {
      const session = await webAgentApi.updateSession(sessionId, { visibility });
      set((state) => ({
        sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
        sharingSessionId: undefined,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to update session access.",
        sharingSessionId: undefined,
      });
    }
  },
  shareSession: async (sessionId, email) => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      return;
    }

    set({ sharingSessionId: sessionId });
    try {
      const session = await webAgentApi.updateSession(sessionId, {
        shareWithEmail: trimmedEmail,
        visibility: "shared",
      });
      set((state) => ({
        sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
        sharingSessionId: undefined,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to share session.",
        sharingSessionId: undefined,
      });
    }
  },
  sendMessage: async (content) => {
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
    const shouldAutoRename = isDefaultSessionTitle(currentSession?.title);
    const autoTitle = generateSessionTitle(trimmed);

    const now = new Date().toISOString();
    const runId = createId("run");
    let currentRunId = runId;
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
      id: runId,
      hasAssistantResponse: false,
      isPlainChat: false,
      progress: 0,
      sessionId,
      startedAt: now,
      status: "running",
      steps: [],
      title: "Hermes request",
    };

    requestAbortControllers.get(sessionId)?.abort();
    const requestAbortController = new AbortController();
    requestAbortControllers.set(sessionId, requestAbortController);

    set((state) => ({
      activeAgentRunId: runId,
      agentRuns: [run, ...state.agentRuns],
      error: undefined,
      messages: [...state.messages, optimisticUserMessage, pendingAssistantMessage],
      selectedArtifactId: state.selectedArtifactId,
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
      void webAgentApi.updateSession(sessionId, { title: autoTitle }).then((session) => {
        set((state) => ({
          sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
        }));
      }).catch((error) => {
        set({ error: error instanceof Error ? error.message : "Failed to rename session." });
      });
    }

    let backendRunDiscoveryTimer: number | undefined;
    const stopBackendRunDiscovery = () => {
      if (backendRunDiscoveryTimer !== undefined) {
        window.clearInterval(backendRunDiscoveryTimer);
        backendRunDiscoveryTimer = undefined;
      }
    };

    {
      const startedAtMs = Date.parse(now);
      backendRunDiscoveryTimer = window.setInterval(() => {
        void webAgentApi.listAgentRuns(sessionId).then((runs) => {
          if (currentRunId !== runId) {
            stopBackendRunDiscovery();
            return;
          }
          const backendRun = runs.find((candidate) => {
            if (
              candidate.id.startsWith("run_") ||
              candidate.sessionId !== sessionId ||
              isTerminalRunStatus(candidate.status)
            ) {
              return false;
            }
            return Date.parse(candidate.startedAt) >= startedAtMs - 10_000;
          });
          if (!backendRun) {
            return;
          }

          const previousRunId = currentRunId;
          currentRunId = bindBackendRunId(currentRunId, backendRun.id);
          set((state) => {
            const boundState = {
              ...state,
              ...applyBackendRunIdBinding(state, previousRunId, currentRunId),
            };
            return {
              activeAgentRunId:
                boundState.activeAgentRunId === runId
                  ? currentRunId
                  : boundState.activeAgentRunId,
              agentRuns: boundState.agentRuns.map((runItem) =>
                runItem.id === currentRunId
                  ? {
                      ...runItem,
                      adapterKey: backendRun.adapterKey,
                      completedAt: backendRun.completedAt,
                      error: backendRun.error,
                      progress: backendRun.progress,
                      queueName: backendRun.queueName,
                      queuePosition: backendRun.queuePosition,
                      queueReason: backendRun.queueReason,
                      startedAt: backendRun.startedAt,
                      status: backendRun.status,
                      steps: backendRun.steps,
                    }
                  : runItem,
              ),
            };
          });
          subscribeAgentRunEvents(get, backendRun.id);
          stopBackendRunDiscovery();
        }).catch(() => {
          // The streaming request still owns visible error reporting.
        });
      }, 1500);
    }

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
            subscribeAgentRunEvents(get, event.runId);
          }
          set((state) => {
            const boundState = {
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
      if (
        !currentRunId.startsWith("run_") &&
        get().agentRuns.some(
          (runItem) => runItem.id === currentRunId && !isTerminalRunStatus(runItem.status),
        )
      ) {
        const refreshedRun = await webAgentApi.getAgentRun(currentRunId);
        set((state) => ({
          activeAgentRunId: isTerminalRunStatus(refreshedRun.status)
            ? undefined
            : state.activeAgentRunId,
          agentRuns: state.agentRuns.map((runItem) =>
            runItem.id === refreshedRun.id ? refreshedRun : runItem,
          ),
        }));
      }
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError";
      set({
        activeAgentRunId: undefined,
        agentRuns: get().agentRuns.map((runItem) =>
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
        messages: get().messages.filter(
          (message) =>
            !(
              message.sessionId === sessionId &&
              message.role === "assistant" &&
              message.isPending
            ),
        ),
      });
    } finally {
      stopBackendRunDiscovery();
      if (requestAbortControllers.get(sessionId) === requestAbortController) {
        requestAbortControllers.delete(sessionId);
      }
    }
  },
  setDefaultModel: async (modelId) => {
    try {
      const models = await settingsApi.setDefaultModel(modelId);
      set({ models, selectedModelId: modelId });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to set model." });
    }
  },
  setDefaultSkill: async (skillKey) => {
    try {
      const skills = await settingsApi.setDefaultSkill(skillKey);
      set({ skills });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to set skill." });
    }
  },
  stopActiveRun: (targetRunId) => {
    const runId = targetRunId ?? get().activeAgentRunId;
    if (!runId) {
      return;
    }

    const runSessionId = get().agentRuns.find((run) => run.id === runId)?.sessionId;
    if (runSessionId) {
      requestAbortControllers.get(runSessionId)?.abort();
      requestAbortControllers.delete(runSessionId);
    }

    void webAgentApi
      .cancelAgentRun(runId)
      .then((run) => {
        set((state) => ({
          activeAgentRunId:
            state.activeAgentRunId === run.id && isTerminalRunStatus(run.status)
              ? undefined
              : state.activeAgentRunId,
          agentRuns: state.agentRuns.some((item) => item.id === run.id)
            ? state.agentRuns.map((item) => (item.id === run.id ? run : item))
            : [run, ...state.agentRuns],
          messages: isTerminalRunStatus(run.status)
            ? state.messages.filter(
                (message) =>
                  !(
                    message.sessionId === run.sessionId &&
                    message.role === "assistant" &&
                    message.isPending
                  ),
              )
            : state.messages,
          sessions: isTerminalRunStatus(run.status)
            ? state.sessions.map((session) =>
                session.id === run.sessionId ? { ...session, status: "active" } : session,
              )
            : state.sessions,
        }));
      })
      .catch((error) => {
        set({ error: error instanceof Error ? error.message : "Failed to cancel run." });
      })
      .finally(() => {
        unsubscribeAgentRun(runId);
      });
  },
  refreshRuntimeModelStatus: async () => {
    set({ runtimeStatusRefreshing: true });
    const runtimeModels = get().models;

    await Promise.all(
      runtimeModels.map(async (model) => {
        try {
          const updatedModel = await settingsApi.testModelConnection(model.id);
          set((state) => ({
            models: state.models.map((item) =>
              item.id === model.id ? { ...item, ...updatedModel } : item,
            ),
          }));
        } catch (error) {
          const message =
            error instanceof Error ? error.message : "Runtime health check failed.";
          set((state) => ({
            models: state.models.map((item) =>
              item.id === model.id
                ? {
                    ...item,
                    isAvailable: false,
                    runtimeStatus: {
                      adapterKey: "hermes",
                      message,
                      ok: false,
                      status: "unavailable",
                    },
                  }
                : item,
            ),
          }));
        }
      }),
    );
    set({
      runtimeStatusCheckedAt: new Date().toISOString(),
      runtimeStatusRefreshing: false,
    });
  },
  testModelConnection: async (modelId) => {
    set({ testingModelId: modelId });
    try {
      const updatedModel = await settingsApi.testModelConnection(modelId);
      set((state) => ({
        models: state.models.map((model) => (model.id === modelId ? updatedModel : model)),
        runtimeStatusCheckedAt: new Date().toISOString(),
        testingModelId: undefined,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to test model.",
        runtimeStatusCheckedAt: new Date().toISOString(),
        testingModelId: undefined,
      });
    }
  },
  toggleSessionPinned: async (sessionId) => {
    const session = get().sessions.find((item) => item.id === sessionId);
    if (!session) {
      return;
    }

    try {
      const updatedSession = await webAgentApi.updateSession(sessionId, {
        pinned: !session.pinned,
      });
      set((state) => ({
        sessions: state.sessions.map((item) =>
          item.id === sessionId ? updatedSession : item,
        ),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to update session." });
    }
  },
  toggleSkillEnabled: async (skillKey) => {
    try {
      const skills = await settingsApi.toggleSkillEnabled(skillKey);
      set({ skills });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to update skill." });
    }
  },
  unshareSession: async (sessionId, userId) => {
    set({ sharingSessionId: sessionId });
    try {
      const session = await webAgentApi.updateSession(sessionId, {
        unshareUserId: userId,
      });
      set((state) => ({
        sessions: state.sessions.map((item) => (item.id === sessionId ? session : item)),
        sharingSessionId: undefined,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to update sharing.",
        sharingSessionId: undefined,
      });
    }
  },
  updateModel: async (modelId, input) => {
    try {
      const updatedModel = await settingsApi.updateModel(modelId, input);
      set((state) => ({
        models: state.models.map((model) => (model.id === modelId ? updatedModel : model)),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to update model." });
    }
  },
  updateSkillVersion: async (skillKey, direction) => {
    set({ updatingSkillKey: skillKey });
    try {
      const skills = await settingsApi.updateSkillVersion(skillKey, direction);
      set({ skills, updatingSkillKey: undefined });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to update skill.",
        updatingSkillKey: undefined,
      });
    }
  },
}));
