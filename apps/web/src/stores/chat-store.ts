"use client";

import { create } from "zustand";
import { subscribeToMockAgentRun, webAgentApi } from "@/services";
import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  Message,
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
  hydrated: boolean;
  loading: boolean;
  messages: Message[];
  selectedArtifactId?: string;
  sessions: Session[];
  skills: Skill[];
  switchingSessionId?: string;
  applyAgentRunEvent: (event: AgentRunEvent) => void;
  createSession: (skillKey?: SkillKey) => Promise<void>;
  hydrate: () => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectSession: (sessionId: string) => void;
  sendMessage: (content: string, skillKey?: SkillKey) => Promise<void>;
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
  selectedArtifactId: undefined,
  sessions: [],
  skills: [],
  switchingSessionId: undefined,
  applyAgentRunEvent: (event) => {
    set((state) => ({
      activeAgentRunId:
        event.status === "completed" ? undefined : state.activeAgentRunId,
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
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to create session.",
      });
    }
  },
  hydrate: async () => {
    if (get().hydrated || get().loading) {
      return;
    }

    set({ error: undefined, loading: true });

    try {
      const [sessions, messages, skills, artifacts] = await Promise.all([
        webAgentApi.listSessions(),
        webAgentApi.listMessages(),
        webAgentApi.listSkills(),
        webAgentApi.listArtifacts(),
      ]);
      const currentSessionId = sessions[0]?.id ?? "";
      const selectedArtifactId =
        artifacts.find((artifact) => artifact.sessionId === currentSessionId)
          ?.id ?? artifacts[0]?.id;

      set({
        artifacts,
        currentSessionId,
        hydrated: true,
        loading: false,
        messages,
        selectedArtifactId,
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
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId }),
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
  sendMessage: async (content, skillKey) => {
    const trimmed = content.trim();

    if (!trimmed) {
      return;
    }

    const sessionId = get().currentSessionId;

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

      const result = await webAgentApi.sendMessage({
        content: trimmed,
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
