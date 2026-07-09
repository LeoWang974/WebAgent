"use client";

import { create } from "zustand";
import { settingsApi, webAgentApi } from "@/services";
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
  sessions: Session[];
  skills: Skill[];
  switchingSessionId?: string;
  testingModelId?: string;
  updatingSkillKey?: SkillKey;
  addModel: (input: Omit<ModelConfig, "id" | "isDefault" | "isAvailable">) => Promise<void>;
  applyAgentRunEvent: (event: AgentRunEvent) => void;
  createSession: (skillKey?: SkillKey) => Promise<Session | undefined>;
  deleteArtifact: (artifactId: string) => void;
  deleteModel: (modelId: string) => Promise<void>;
  deleteSession: (sessionId: string) => void;
  hydrate: () => Promise<void>;
  retryHydrate: () => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectModel: (modelId: string) => void;
  selectSession: (sessionId: string) => void;
  sendMessage: (content: string, skillKey?: SkillKey) => Promise<void>;
  setDefaultModel: (modelId: string) => Promise<void>;
  setDefaultSkill: (skillKey: SkillKey) => Promise<void>;
  stopActiveRun: () => void;
  testModelConnection: (modelId: string) => Promise<void>;
  toggleSessionPinned: (sessionId: string) => void;
  toggleSkillEnabled: (skillKey: SkillKey) => Promise<void>;
  updateModel: (modelId: string, input: Partial<ModelConfig>) => Promise<void>;
  updateSkillVersion: (skillKey: SkillKey, direction: "update" | "rollback") => Promise<void>;
}

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
}

let activeRequestAbortController: AbortController | undefined;
let feedbackTimers: number[] = [];

function clearFeedbackTimers() {
  feedbackTimers.forEach((timer) => window.clearTimeout(timer));
  feedbackTimers = [];
}

function detectRequestedSkill(content: string, explicitSkillKey?: SkillKey) {
  if (explicitSkillKey) {
    return explicitSkillKey;
  }

  const match = content.match(/\b(sn-[a-z0-9-]+)\b/i);
  return match?.[1];
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

function scheduleFeedback({
  modelName,
  requestedSkill,
  runId,
  sessionId,
  set,
}: {
  modelName: string;
  requestedSkill?: string;
  runId: string;
  sessionId: string;
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void;
}) {
  const steps = [
    {
      delay: 900,
      detail: requestedSkill
        ? `Detected ${requestedSkill}. Preparing runtime context and parameters.`
        : "Parsing the request and deciding whether tools or skills are needed.",
      stage: "Parsing request",
    },
    {
      delay: 2200,
      detail: `The request is now running in ${modelName}. Hermes output will stream into the conversation as it appears.`,
      stage: "Calling Hermes",
    },
    {
      delay: 4800,
      detail: requestedSkill
        ? `${modelName} is working through ${requestedSkill}. Tool and subtask messages will be appended below when Hermes prints them.`
        : `${modelName} is working. Tool and subtask messages will be appended below when Hermes prints them.`,
      stage: "Running tools and skills",
    },
    {
      delay: 9000,
      detail: "Waiting for structured output. Long reports and deep research requests can take longer.",
      stage: "Organizing content",
    },
    {
      delay: 15000,
      detail: "Still running. Keep this page open; new Hermes output will continue to stream here.",
      stage: "Waiting for final response",
    },
  ];

  feedbackTimers = steps.map((step) =>
    window.setTimeout(() => {
      set((state) =>
        state.activeAgentRunId === runId
          ? {
              agentFeedback: {
                detail: step.detail,
                modelName,
                sessionId,
                stage: step.stage,
              },
            }
          : {},
      );
    }, step.delay),
  );
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
  selectedArtifactId: undefined,
  selectedModelId: undefined,
  sessions: [],
  skills: [],
  switchingSessionId: undefined,
  testingModelId: undefined,
  updatingSkillKey: undefined,
  applyAgentRunEvent: (event) => {
    const terminalStatuses = ["completed", "failed", "cancelled"];

    set((state) => ({
      activeAgentRunId:
        terminalStatuses.includes(event.status)
          ? undefined
          : state.activeAgentRunId,
      agentRuns: state.agentRuns.map((run) => {
        if (run.id !== event.runId) {
          return run;
        }

        const previousSteps = run.steps.map((step) =>
          step.status === "running"
            ? { ...step, status: "completed" as const }
            : step,
        );

        return {
          ...run,
          completedAt: event.completedAt,
          error: event.error,
          progress: event.progress,
          status: event.status,
          steps: [...previousSteps, event.step],
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
    set((state) => {
      const artifacts = state.artifacts.filter((artifact) => artifact.id !== artifactId);
      const selectedArtifactId =
        state.selectedArtifactId === artifactId
          ? artifacts.find((artifact) => artifact.sessionId === state.currentSessionId)?.id ??
            artifacts[0]?.id
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
      const currentSessionId = sessions[0]?.id ?? "";
      const selectedArtifactId =
        artifacts.find((artifact) => artifact.sessionId === currentSessionId)?.id ??
        artifacts[0]?.id;
      const selectedModelId = models.find((model) => model.isDefault)?.id ?? models[0]?.id;

      set({
        artifacts,
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
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId }),
  selectModel: (modelId) => set({ selectedModelId: modelId }),
  selectSession: (sessionId) => {
    const artifact = get().artifacts.find((item) => item.sessionId === sessionId);
    set({ currentSessionId: sessionId, selectedArtifactId: artifact?.id });
    setSwitchingState(set, get, sessionId);
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
    if (!sessionId) {
      return;
    }

    const now = new Date().toISOString();
    const runId = createId("run");
    const optimisticUserMessage: Message = {
      id: createId("message_user"),
      sessionId,
      role: "user",
      content: trimmed,
      createdAt: now,
    };
    const run: AgentRun = {
      id: runId,
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
      agentFeedback: {
        detail: requestedSkill
          ? `Detected ${requestedSkill}. Sending the request to ${modelName}.`
          : `Sending the request to ${modelName}.`,
        modelName,
        sessionId,
        stage: "Request received",
      },
      agentRuns: [run, ...state.agentRuns],
      error: undefined,
      messages: [...state.messages, optimisticUserMessage],
      sessions: state.sessions.map((session) =>
        session.id === sessionId ? { ...session, status: "running", updatedAt: now } : session,
      ),
    }));

    scheduleFeedback({ modelName, requestedSkill, runId, sessionId, set });

    try {
      await webAgentApi.sendMessageStream(
        {
          content: trimmed,
          modelId,
          signal: activeRequestAbortController.signal,
          sessionId,
          skillKey,
        },
        (event) => {
          if (event.type === "assistant_delta") {
            const chunk = event.content.trim();
            if (!chunk) {
              return;
            }

            set((state) => {
              const existing = state.messages.find((message) => message.id === event.messageId);
              const nextContent = existing?.content
                ? `${existing.content}\n${chunk}`
                : chunk;

              return {
                agentFeedback: {
                  detail: "Hermes produced a new update. It has been appended to the assistant message below.",
                  modelName,
                  sessionId,
                  stage: "Streaming Hermes output",
                },
                messages: existing
                  ? state.messages.map((message) =>
                      message.id === event.messageId
                        ? { ...message, content: nextContent }
                        : message,
                    )
                  : [
                      ...state.messages,
                      {
                        id: event.messageId,
                        sessionId,
                        role: "assistant",
                        content: chunk,
                        createdAt: new Date().toISOString(),
                      },
                    ],
              };
            });
          }

          if (event.type === "assistant_done") {
            set((state) => ({
              activeAgentRunId:
                state.activeAgentRunId === runId ? undefined : state.activeAgentRunId,
              agentFeedback:
                state.activeAgentRunId === runId ? undefined : state.agentFeedback,
              agentRuns: state.agentRuns.map((runItem) =>
                runItem.id === runId
                  ? {
                      ...runItem,
                      completedAt: new Date().toISOString(),
                      progress: 100,
                      status: "completed",
                    }
                  : runItem,
              ),
              messages: state.messages.some((message) => message.id === event.message.id)
                ? state.messages.map((message) =>
                    message.id === event.message.id ? event.message : message,
                  )
                : [...state.messages, event.message],
              sessions: state.sessions.map((session) =>
                session.id === event.session.id ? event.session : session,
              ),
            }));
          }
        },
      );
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError";
      set({
        activeAgentRunId: undefined,
        agentFeedback: undefined,
        agentRuns: get().agentRuns.map((runItem) =>
          runItem.id === runId
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
      });
    } finally {
      clearFeedbackTimers();
      if (get().activeAgentRunId !== runId) {
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

    activeRequestAbortController?.abort();
    activeRequestAbortController = undefined;
    clearFeedbackTimers();

    set((state) => ({
      activeAgentRunId: undefined,
      agentFeedback: undefined,
      agentRuns: state.agentRuns.map((run) =>
        run.id === runId
          ? { ...run, completedAt: new Date().toISOString(), status: "cancelled" }
          : run,
      ),
      sessions: state.sessions.map((session) =>
        session.id === state.currentSessionId ? { ...session, status: "active" } : session,
      ),
    }));
  },
  testModelConnection: async (modelId) => {
    set({ testingModelId: modelId });
    try {
      const updatedModel = await settingsApi.testModelConnection(modelId);
      set((state) => ({
        models: state.models.map((model) => (model.id === modelId ? updatedModel : model)),
        testingModelId: undefined,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to test model.",
        testingModelId: undefined,
      });
    }
  },
  toggleSessionPinned: (sessionId) => {
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
