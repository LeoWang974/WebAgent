"use client";

import { create } from "zustand";
import { shouldSelectCreatedArtifact } from "@/lib/artifact-selection";
import { settingsApi, webAgentApi } from "@/services";
import type { AgentRunUnsubscribe } from "@/services/adapters/types";
import { useUiStore } from "./ui-store";
import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  Message,
  ModelConfig,
  Session,
  Skill,
  SkillKey,
} from "@/types";

interface AgentFeedback {
  detail: string;
  modelName: string;
  sessionId: string;
  stage: string;
  startedAt: string;
}

interface ChatState {
  activeAgentRunId?: string;
  agentFeedback?: AgentFeedback;
  agentRuns: AgentRun[];
  artifacts: Artifact[];
  currentSessionId: string;
  error?: string;
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
  createSession: (skillKey?: SkillKey) => Promise<Session | undefined>;
  deleteArtifact: (artifactId: string) => void;
  deleteModel: (modelId: string) => Promise<void>;
  deleteSession: (sessionId: string) => void;
  hydrate: () => Promise<void>;
  resetWorkspace: () => void;
  retryHydrate: () => Promise<void>;
  refreshRuntimeModelStatus: () => Promise<void>;
  refreshAgentRun: (runId: string) => Promise<AgentRun | undefined>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectModel: (modelId: string) => void;
  selectSession: (sessionId: string) => void;
  setSessionVisibility: (sessionId: string, visibility: Session["visibility"]) => Promise<void>;
  shareSession: (sessionId: string, email: string) => Promise<void>;
  sendMessage: (content: string, skillKey?: SkillKey) => Promise<void>;
  setDefaultModel: (modelId: string) => Promise<void>;
  setDefaultSkill: (skillKey: SkillKey) => Promise<void>;
  stopActiveRun: () => void;
  testModelConnection: (modelId: string) => Promise<void>;
  toggleSessionPinned: (sessionId: string) => void;
  toggleSkillEnabled: (skillKey: SkillKey) => Promise<void>;
  unshareSession: (sessionId: string, userId: string) => Promise<void>;
  updateModel: (modelId: string, input: Partial<ModelConfig>) => Promise<void>;
  updateSkillVersion: (skillKey: SkillKey, direction: "update" | "rollback") => Promise<void>;
}

function createId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

let activeRequestAbortController: AbortController | undefined;
let feedbackTimers: number[] = [];
const agentRunUnsubscribers = new Map<string, AgentRunUnsubscribe>();
const TERMINAL_RUN_STATUSES: AgentRun["status"][] = [
  "completed",
  "failed",
  "cancelled",
  "disconnected",
];

function clearFeedbackTimers() {
  feedbackTimers.forEach((timer) => window.clearTimeout(timer));
  feedbackTimers = [];
}

function isTerminalRunStatus(status: AgentRun["status"]) {
  return TERMINAL_RUN_STATUSES.includes(status);
}

function unsubscribeAgentRun(runId: string) {
  agentRunUnsubscribers.get(runId)?.();
  agentRunUnsubscribers.delete(runId);
}

function subscribeAgentRunEvents(
  get: () => ChatState,
  runId: string,
) {
  if (agentRunUnsubscribers.has(runId)) {
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
}

function detectRequestedSkill(content: string, explicitSkillKey?: SkillKey): SkillKey | undefined {
  if (explicitSkillKey) {
    return explicitSkillKey;
  }

  const normalized = content.toLowerCase();
  const skillAliases: Array<[SkillKey, string[]]> = [
    ["deep_research", ["sn-deep-research", "deep research", "深度调研", "调研", "研究报告"]],
    ["data_analysis", ["sn-da", "data analysis", "数据分析", "分析数据", "表格分析"]],
    ["ppt_generation", ["sn-ppt", "ppt", "幻灯片", "演示文稿"]],
    ["u1_image", ["u1", "生图", "生成图片", "图片生成"]],
  ];

  return skillAliases.find(([, aliases]) =>
    aliases.some((alias) => normalized.includes(alias.toLowerCase())),
  )?.[0];
}

function isDefaultSessionTitle(title?: string) {
  const normalized = (title ?? "").trim().toLowerCase();
  return !normalized || normalized === "新对话" || normalized === "new conversation";
}

function generateSessionTitle(content: string, skillKey?: SkillKey) {
  const skillPrefix: Record<SkillKey, string> = {
    data_analysis: "数据分析",
    deep_research: "深度调研",
    ppt_generation: "PPT生成",
    u1_image: "图像生成",
  };
  const cleaned = content
    .replace(/[`*_>#\[\]{}()（）《》"“”'‘’]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^(请|帮我|帮我一下|麻烦|使用|基于|最后|现在|接下来|生成|分析|写一份|做一份)+/i, "")
    .trim();
  const compact = cleaned.length > 22 ? `${cleaned.slice(0, 22)}...` : cleaned;
  const fallback = skillKey ? skillPrefix[skillKey] : "新任务";
  return compact ? `${skillKey ? `${skillPrefix[skillKey]}：` : ""}${compact}` : fallback;
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

function bindBackendRunId(
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void,
  localRunId: string,
  backendRunId?: string,
) {
  if (!backendRunId || backendRunId === localRunId) {
    return localRunId;
  }

  set((state) => ({
    activeAgentRunId:
      state.activeAgentRunId === localRunId ? backendRunId : state.activeAgentRunId,
    agentRuns: state.agentRuns.map((run) =>
      run.id === localRunId ? { ...run, id: backendRunId } : run,
    ),
  }));
  return backendRunId;
}

function createPendingAssistantMessage(
  sessionId: string,
  modelName: string,
  requestedSkill?: string,
): Message {
  const now = new Date().toISOString();
  const language = useUiStore.getState().language;
  const pendingLabel = requestedSkill
    ? language === "zh-CN"
      ? `${modelName} 正在执行 ${requestedSkill}，等待阶段反馈...`
      : `${modelName} is running ${requestedSkill} and waiting for runtime updates...`
    : language === "zh-CN"
      ? `${modelName} 正在工作，等待运行状态...`
      : `${modelName} is working and waiting for runtime updates...`;

  return {
    id: createId("message_assistant_pending"),
    sessionId,
    role: "assistant",
    content: "",
    createdAt: now,
    isPending: true,
    pendingLabel,
    waitStartedAt: now,
  };
}

export const useChatStore = create<ChatState>((set, get) => ({
  activeAgentRunId: undefined,
  agentFeedback: undefined,
  agentRuns: [],
  artifacts: [],
  currentSessionId: "",
  error: undefined,
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
    set((state) => ({
      activeAgentRunId:
        state.activeAgentRunId === event.runId && isTerminalRunStatus(event.status)
          ? undefined
          : state.activeAgentRunId,
      agentRuns: state.agentRuns.map((run) => {
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

        return {
          ...run,
          completedAt: event.completedAt,
          error: event.error,
          progress: event.progress,
          status: event.status,
          steps: hasExistingStep ? previousSteps : [...previousSteps, event.step],
        };
      }),
    }));
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
  createSession: async (skillKey) => {
    set({ error: undefined });
    try {
      const session = await webAgentApi.createSession({ skillKey });
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
  deleteArtifact: (artifactId) => {
    void webAgentApi.deleteArtifact(artifactId).catch((error) => {
      set({ error: error instanceof Error ? error.message : "Failed to delete artifact." });
    });

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
    const model = get().models.find((item) => item.id === modelId);
    if (model?.isDefault) {
      return;
    }

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
  deleteSession: (sessionId) => {
    void webAgentApi.deleteSession(sessionId).catch((error) => {
      set({ error: error instanceof Error ? error.message : "Failed to delete session." });
    });

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
        agentFeedback:
          state.agentFeedback?.sessionId === sessionId ? undefined : state.agentFeedback,
        agentRuns: state.agentRuns.filter((run) => run.sessionId !== sessionId),
        artifacts: state.artifacts.filter((artifact) => artifact.sessionId !== sessionId),
        currentSessionId,
        messages: state.messages.filter((message) => message.sessionId !== sessionId),
        selectedArtifactId,
        sessions,
        switchingSessionId: state.switchingSessionId === sessionId ? undefined : state.switchingSessionId,
      };
    });
  },
  hydrate: async () => {
    if (get().hydrated || get().loading) {
      return;
    }

    set({ error: undefined, loading: true });
    try {
      const [sessions, messages, skills, artifacts, models] = await Promise.all([
        webAgentApi.listSessions(),
        webAgentApi.listMessages(),
        webAgentApi.listSkills(),
        webAgentApi.listArtifacts(),
        webAgentApi.listModels(),
      ]);
      const agentRuns = await webAgentApi.listAgentRuns();
      const currentSessionId = sessions[0]?.id ?? "";
      const activeRun = agentRuns.find(
        (run) => run.sessionId === currentSessionId && !isTerminalRunStatus(run.status),
      );
      const selectedArtifactId =
        artifacts.find((artifact) => artifact.sessionId === currentSessionId)?.id;
      const selectedModelId = models.find((model) => model.isDefault)?.id ?? models[0]?.id;

      set({
        artifacts,
        activeAgentRunId: activeRun?.id,
        agentRuns,
        currentSessionId,
        hydrated: true,
        loading: false,
        messages,
        models,
        selectedArtifactId,
        selectedModelId,
        sessions,
        skills,
      });
      void get().refreshRuntimeModelStatus();
      agentRuns
        .filter((run) => !isTerminalRunStatus(run.status))
        .forEach((run) => subscribeAgentRunEvents(get, run.id));
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
  resetWorkspace: () => {
    activeRequestAbortController?.abort();
    activeRequestAbortController = undefined;
    clearFeedbackTimers();
    agentRunUnsubscribers.forEach((unsubscribe) => unsubscribe());
    agentRunUnsubscribers.clear();

    set({
      activeAgentRunId: undefined,
      agentFeedback: undefined,
      agentRuns: [],
      artifacts: [],
      currentSessionId: "",
      error: undefined,
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
    try {
      const run = await webAgentApi.getAgentRun(runId);
      set((state) => ({
        agentRuns: state.agentRuns.some((item) => item.id === run.id)
          ? state.agentRuns.map((item) => (item.id === run.id ? run : item))
          : [run, ...state.agentRuns],
      }));
      return run;
    } catch (error) {
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
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId }),
  selectModel: (modelId) => set({ selectedModelId: modelId }),
  selectSession: (sessionId) => {
    const artifact = get().artifacts.find((item) => item.sessionId === sessionId);
    const activeRun = get().agentRuns.find(
      (run) => run.sessionId === sessionId && !isTerminalRunStatus(run.status),
    );
    set({
      activeAgentRunId: activeRun?.id,
      currentSessionId: sessionId,
      selectedArtifactId: artifact?.id,
    });
    if (activeRun) {
      subscribeAgentRunEvents(get, activeRun.id);
    }
    setSwitchingState(set, get, sessionId);
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
  sendMessage: async (content, skillKey) => {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    const sessionId = get().currentSessionId;
    const modelId = get().selectedModelId;
    const modelName = get().models.find((model) => model.id === modelId)?.name ?? "Agent";
    const requestedSkill = detectRequestedSkill(trimmed, skillKey);
    const currentSession = get().sessions.find((session) => session.id === sessionId);
    const shouldAutoRename = isDefaultSessionTitle(currentSession?.title);
    const autoTitle = generateSessionTitle(trimmed, requestedSkill);
    if (!sessionId) {
      return;
    }

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
      requestedSkill,
    );
    const run: AgentRun = {
      id: runId,
      hasAssistantResponse: false,
      isPlainChat: !requestedSkill,
      progress: 0,
      sessionId,
      startedAt: now,
      status: "running",
      steps: [],
      title: skillKey ? "Selected skill request" : "Agent request",
    };

    activeRequestAbortController?.abort();
    activeRequestAbortController = new AbortController();
    clearFeedbackTimers();

    set((state) => ({
      activeAgentRunId: runId,
      agentFeedback: undefined,
      agentRuns: [run, ...state.agentRuns],
      error: undefined,
      messages: [...state.messages, optimisticUserMessage, pendingAssistantMessage],
      selectedArtifactId: requestedSkill ? state.selectedArtifactId : undefined,
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

    try {
      await webAgentApi.sendMessageStream(
        {
          content: trimmed,
          modelId,
          signal: activeRequestAbortController.signal,
          sessionId,
          skillKey: requestedSkill,
        },
        (event) => {
          currentRunId = bindBackendRunId(
            set,
            currentRunId,
            "runId" in event ? event.runId : undefined,
          );

          if (event.type === "run_started") {
            set((state) => ({
              activeAgentRunId:
                state.activeAgentRunId === currentRunId ? event.runId : state.activeAgentRunId,
              agentRuns: state.agentRuns.map((runItem) =>
                runItem.id === event.runId
                  ? {
                      ...runItem,
                      progress: event.progress,
                      status: event.status,
                    }
                  : runItem,
              ),
            }));
            return;
          }

          if (event.type === "assistant_delta") {
            const chunk = event.content.trim();
            if (!chunk) {
              return;
            }

            clearFeedbackTimers();

            set((state) => {
              const now = new Date().toISOString();
              const currentRun = state.agentRuns.find((runItem) => runItem.id === currentRunId);
              const nextProgress = Math.min(90, (currentRun?.progress ?? 5) + 8);
              const pendingIndex = state.messages.findIndex(
                (message) =>
                  message.sessionId === sessionId &&
                  message.role === "assistant" &&
                  message.isPending,
              );
              const completedMessage: Message = {
                id: event.messageId,
                sessionId,
                role: "assistant",
                content: chunk,
                createdAt: now,
                waitStartedAt:
                  pendingIndex >= 0
                    ? state.messages[pendingIndex].waitStartedAt
                    : undefined,
              };
              const nextPendingMessage = createPendingAssistantMessage(
                sessionId,
                modelName,
                requestedSkill,
              );
              const shouldCreateNextPending = Boolean(requestedSkill);

              if (pendingIndex >= 0) {
                return {
                  agentFeedback: undefined,
                  agentRuns: state.agentRuns.map((runItem) =>
                    runItem.id === currentRunId
                      ? {
                          ...runItem,
                          hasAssistantResponse: true,
                          progress: nextProgress,
                          status: "running",
                          steps: [
                            ...runItem.steps.map((step) =>
                              step.status === "running"
                                ? { ...step, status: "completed" as const }
                                : step,
                            ),
                            {
                              id: event.messageId,
                              label: chunk,
                              status: "completed",
                              timestamp: now,
                            },
                          ],
                        }
                      : runItem,
                  ),
                  messages: [
                    ...state.messages.slice(0, pendingIndex),
                    completedMessage,
                    ...(shouldCreateNextPending ? [nextPendingMessage] : []),
                    ...state.messages.slice(pendingIndex + 1),
                  ],
                };
              }

              return {
                agentFeedback: undefined,
                agentRuns: state.agentRuns.map((runItem) =>
                  runItem.id === currentRunId
                    ? {
                        ...runItem,
                        hasAssistantResponse: true,
                        progress: nextProgress,
                        status: "running",
                        steps: [
                          ...runItem.steps.map((step) =>
                            step.status === "running"
                              ? { ...step, status: "completed" as const }
                              : step,
                          ),
                          {
                            id: event.messageId,
                            label: chunk,
                            status: "completed",
                            timestamp: now,
                          },
                        ],
                      }
                    : runItem,
                ),
                messages: [
                  ...state.messages,
                  completedMessage,
                  ...(shouldCreateNextPending ? [nextPendingMessage] : []),
                ],
              };
            });
          }

          if (event.type === "artifact_created") {
            set((state) => {
              const currentSelectedArtifact = state.artifacts.find(
                (artifact) => artifact.id === state.selectedArtifactId,
              );
              const targetMessage = state.messages.find(
                (message) => message.id === event.messageId,
              );
              const selectedBelongsToTargetMessage =
                !!state.selectedArtifactId &&
                !!targetMessage?.artifactIds?.includes(state.selectedArtifactId);
              const artifacts = state.artifacts.some(
                (artifact) => artifact.id === event.artifact.id,
              )
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
                        artifactIds: Array.from(
                          new Set([...(message.artifactIds ?? []), event.artifact.id]),
                        ),
                      }
                    : message,
                ),
                selectedArtifactId: shouldSelectArtifact
                  ? event.artifact.id
                  : state.selectedArtifactId,
              };
            });
          }

          if (event.type === "assistant_done") {
            set((state) => {
              const finalStatus = event.status ?? "completed";
              const existingMessage = state.messages.find(
                (message) => message.id === event.message.id,
              );
              const pendingIndex = state.messages.findIndex(
                (message) =>
                  message.sessionId === sessionId &&
                  message.role === "assistant" &&
                  message.isPending,
              );
              let messages = state.messages.filter(
                (message) =>
                  !(
                    message.sessionId === sessionId &&
                    message.role === "assistant" &&
                    message.isPending
                  ),
              );

              if (existingMessage) {
                messages = messages.map((message) =>
                  message.id === event.message.id
                    ? {
                        ...event.message,
                        waitStartedAt: existingMessage.waitStartedAt,
                      }
                    : message,
                );
              } else if (pendingIndex >= 0) {
                messages = [
                  ...state.messages.slice(0, pendingIndex),
                  {
                    ...event.message,
                    waitStartedAt: state.messages[pendingIndex].waitStartedAt,
                  },
                  ...state.messages.slice(pendingIndex + 1).filter((message) => !message.isPending),
                ];
              } else {
                messages = [...messages, event.message];
              }

              return {
                activeAgentRunId:
                  state.activeAgentRunId === currentRunId ? undefined : state.activeAgentRunId,
                agentFeedback:
                  state.activeAgentRunId === currentRunId ? undefined : state.agentFeedback,
                agentRuns: state.agentRuns.map((runItem) =>
                  runItem.id === currentRunId
                    ? {
                      ...runItem,
                        completedAt: new Date().toISOString(),
                        hasAssistantResponse: true,
                        progress: finalStatus === "completed" ? 100 : runItem.progress,
                        status: finalStatus,
                      }
                    : runItem,
                ),
                messages,
                sessions: state.sessions.map((session) =>
                  session.id === event.session.id ? event.session : session,
                ),
              };
            });
          }
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
        agentFeedback: undefined,
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
      clearFeedbackTimers();
      if (get().activeAgentRunId !== currentRunId) {
        activeRequestAbortController = undefined;
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
  stopActiveRun: () => {
    const runId = get().activeAgentRunId;
    if (!runId) {
      return;
    }

    void webAgentApi
      .cancelAgentRun(runId)
      .then((run) => {
        set((state) => ({
          agentRuns: state.agentRuns.map((item) => (item.id === run.id ? run : item)),
        }));
      })
      .catch((error) => {
        set({ error: error instanceof Error ? error.message : "Failed to cancel run." });
      })
      .finally(() => {
        unsubscribeAgentRun(runId);
        activeRequestAbortController?.abort();
        activeRequestAbortController = undefined;
      });
    clearFeedbackTimers();

    set((state) => ({
      activeAgentRunId: undefined,
      agentFeedback: undefined,
      agentRuns: state.agentRuns.map((run) =>
        run.id === runId
          ? { ...run, completedAt: new Date().toISOString(), status: "cancelled" }
          : run,
      ),
      messages: state.messages.filter(
        (message) =>
          !(
            message.sessionId === state.currentSessionId &&
            message.role === "assistant" &&
            message.isPending
          ),
      ),
      sessions: state.sessions.map((session) =>
        session.id === state.currentSessionId ? { ...session, status: "active" } : session,
      ),
    }));
  },
  refreshRuntimeModelStatus: async () => {
    set({ runtimeStatusRefreshing: true });
    const runtimeModels = get().models.filter((model) => {
      const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
      return (
        marker.includes("openclaw") ||
        marker.includes("hermes") ||
        marker.includes("18789") ||
        marker.includes("8642")
      );
    });

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
                      adapterKey: item.name.toLowerCase().includes("openclaw")
                        ? "openclaw"
                        : item.name.toLowerCase().includes("hermes")
                          ? "hermes"
                          : undefined,
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
  toggleSessionPinned: (sessionId) => {
    const session = get().sessions.find((item) => item.id === sessionId);
    if (session) {
      void webAgentApi.updateSession(sessionId, { pinned: !session.pinned }).catch((error) => {
        set({ error: error instanceof Error ? error.message : "Failed to update session." });
      });
    }

    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === sessionId ? { ...session, pinned: !session.pinned } : session,
      ),
    }));
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
