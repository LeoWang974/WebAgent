"use client";

import { create } from "zustand";
import { subscribeToMockAgentRun, webAgentApi } from "@/services";
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

interface ChatState {
  activeAgentRunId?: string;
  agentRuns: AgentRun[];
  artifacts: Artifact[];
  currentSessionId: string;
  deleteArtifact: (artifactId: string) => void;
  deleteSession: (sessionId: string) => void;
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
  applyAgentRunEvent: (event: AgentRunEvent) => void;
  createSession: (skillKey?: SkillKey) => Promise<Session | undefined>;
  hydrate: () => Promise<void>;
  retryHydrate: () => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectModel: (modelId: string) => void;
  selectSession: (sessionId: string) => void;
  sendMessage: (content: string, skillKey?: SkillKey) => Promise<void>;
  toggleSessionPinned: (sessionId: string) => void;
}

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
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

export const useChatStore = create<ChatState>((set, get) => ({
  activeAgentRunId: undefined,
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
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to create session.",
      });
      return undefined;
    }
  },
  deleteArtifact: (artifactId) => {
    set((state) => {
      const artifacts = state.artifacts.filter(
        (artifact) => artifact.id !== artifactId,
      );
      const selectedArtifactId =
        state.selectedArtifactId === artifactId
          ? artifacts.find(
              (artifact) => artifact.sessionId === state.currentSessionId,
            )?.id ?? artifacts[0]?.id
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
  deleteSession: (sessionId) => {
    set((state) => {
      const sessions = state.sessions.filter(
        (session) => session.id !== sessionId,
      );
      const currentSessionId =
        state.currentSessionId === sessionId
          ? sessions[0]?.id ?? ""
          : state.currentSessionId;
      const selectedArtifactId =
        state.currentSessionId === sessionId
          ? state.artifacts.find(
              (artifact) => artifact.sessionId === currentSessionId,
            )?.id
          : state.selectedArtifactId;

      return {
        activeAgentRunId:
          state.agentRuns.find(
            (run) => run.id === state.activeAgentRunId,
          )?.sessionId === sessionId
            ? undefined
            : state.activeAgentRunId,
        agentRuns: state.agentRuns.filter((run) => run.sessionId !== sessionId),
        artifacts: state.artifacts.filter(
          (artifact) => artifact.sessionId !== sessionId,
        ),
        currentSessionId,
        messages: state.messages.filter(
          (message) => message.sessionId !== sessionId,
        ),
        selectedArtifactId,
        sessions,
        switchingSessionId:
          state.switchingSessionId === sessionId
            ? undefined
            : state.switchingSessionId,
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
        artifacts.find((artifact) => artifact.sessionId === currentSessionId)
          ?.id ?? artifacts[0]?.id;
      const selectedModelId =
        models.find((model) => model.isDefault)?.id ?? models[0]?.id;

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
        error:
          error instanceof Error
            ? error.message
            : "Failed to load workspace data.",
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
    const artifact = get().artifacts.find(
      (item) => item.sessionId === sessionId,
    );

    set({
      currentSessionId: sessionId,
      selectedArtifactId: artifact?.id,
    });
    setSwitchingState(set, get, sessionId);
  },
  toggleSessionPinned: (sessionId) => {
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              pinned: !session.pinned,
            }
          : session,
      ),
    }));
  },
  sendMessage: async (content, skillKey) => {
    const trimmed = content.trim();

    if (!trimmed) {
      return;
    }

    const sessionId = get().currentSessionId;
    const modelId = get().selectedModelId;

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
      status: "queued",
      steps: [],
      title: skillKey ? "Running selected skill" : "Running agent",
    };

    set((state) => ({
      activeAgentRunId: runId,
      agentRuns: [run, ...state.agentRuns],
      error: undefined,
      messages: [...state.messages, optimisticUserMessage],
      sessions: state.sessions.map((session) =>
        session.id === sessionId
          ? { ...session, status: "running", updatedAt: now }
          : session,
      ),
    }));

    let unsubscribe = () => {};

    try {
      await new Promise<void>((resolve) => {
        unsubscribe = subscribeToMockAgentRun({
          onEvent: (event) => {
            get().applyAgentRunEvent(event);

            if (event.status === "completed") {
              resolve();
            }
          },
          runId,
        });
      });
      unsubscribe();

      const result = await webAgentApi.sendMessage({
        content: trimmed,
        modelId,
        sessionId,
        skillKey,
      });
      const assistantMessages = result.messages.filter(
        (message) => message.role === "assistant",
      );

      set((state) => ({
        messages: [...state.messages, ...assistantMessages],
        sessions: state.sessions.map((session) =>
          session.id === result.session.id ? result.session : session,
        ),
      }));
    } catch (error) {
      unsubscribe();
      set({
        activeAgentRunId: undefined,
        agentRuns: get().agentRuns.map((runItem) =>
          runItem.id === runId
            ? {
                ...runItem,
                completedAt: new Date().toISOString(),
                error:
                  error instanceof Error
                    ? error.message
                    : "Failed to send message.",
                status: "failed",
              }
            : runItem,
        ),
        error:
          error instanceof Error ? error.message : "Failed to send message.",
      });
    }
  },
}));
