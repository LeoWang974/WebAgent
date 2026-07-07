"use client";

import { create } from "zustand";
import type { Artifact, Message, Session, Skill, SkillKey } from "@/types";
import {
  mockArtifacts,
  mockMessages,
  mockSessions,
  mockSkills,
} from "@/services/mock-data";

interface ChatState {
  sessions: Session[];
  messages: Message[];
  skills: Skill[];
  artifacts: Artifact[];
  currentSessionId: string;
  selectedArtifactId?: string;
  selectSession: (sessionId: string) => void;
  selectArtifact: (artifactId: string) => void;
  createSession: (skillKey?: SkillKey) => void;
  sendMessage: (content: string, skillKey?: SkillKey) => void;
}

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: mockSessions,
  messages: mockMessages,
  skills: mockSkills,
  artifacts: mockArtifacts,
  currentSessionId: mockSessions[0]?.id ?? "",
  selectedArtifactId: mockArtifacts[0]?.id,
  selectSession: (sessionId) => {
    const artifact = get().artifacts.find(
      (item) => item.sessionId === sessionId,
    );
    set({
      currentSessionId: sessionId,
      selectedArtifactId: artifact?.id,
    });
  },
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId }),
  createSession: (skillKey) => {
    const now = new Date().toISOString();
    const session: Session = {
      id: createId("session"),
      title: skillKey ? "新的 Skill 会话" : "新的对话",
      type: skillKey ?? "chat",
      pinned: false,
      status: "active",
      updatedAt: now,
    };

    set((state) => ({
      sessions: [session, ...state.sessions],
      currentSessionId: session.id,
      selectedArtifactId: undefined,
    }));
  },
  sendMessage: (content, skillKey) => {
    const trimmed = content.trim();

    if (!trimmed) {
      return;
    }

    const state = get();
    const sessionId = state.currentSessionId;
    const now = new Date().toISOString();
    const userMessage: Message = {
      id: createId("message_user"),
      sessionId,
      role: "user",
      content: trimmed,
      createdAt: now,
    };
    const assistantMessage: Message = {
      id: createId("message_assistant"),
      sessionId,
      role: "assistant",
      content: skillKey
        ? `已进入 ${state.skills.find((skill) => skill.key === skillKey)?.name ?? "Skill"} 模式。后续会接入真实 Agent 执行。`
        : "这是 mock 回复。后续会接入 FastAPI、SSE 和 Agent Runtime。",
      createdAt: now,
    };

    set((current) => ({
      messages: [...current.messages, userMessage, assistantMessage],
      sessions: current.sessions.map((session) =>
        session.id === sessionId
          ? { ...session, status: "active", updatedAt: now }
          : session,
      ),
    }));
  },
}));

