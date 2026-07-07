"use client";

import { create } from "zustand";
import { webAgentApi } from "@/services";
import type { Artifact, Message, Session, Skill, SkillKey } from "@/types";

interface ChatState {
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
  createSession: (skillKey?: SkillKey) => Promise<void>;
  hydrate: () => Promise<void>;
  selectArtifact: (artifactId: string) => void;
  selectSession: (sessionId: string) => void;
  sendMessage: (content: string, skillKey?: SkillKey) => Promise<void>;
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

    set({ error: undefined });

    try {
      const result = await webAgentApi.sendMessage({
        content: trimmed,
        sessionId,
        skillKey,
      });

      set((state) => ({
        messages: [...state.messages, ...result.messages],
        sessions: state.sessions.map((session) =>
          session.id === result.session.id ? result.session : session,
        ),
      }));
    } catch (error) {
      set({
        error:
          error instanceof Error ? error.message : "Failed to send message.",
      });
    }
  },
}));

