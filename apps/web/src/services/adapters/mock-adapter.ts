import type {
  CreateSessionInput,
  SendMessageInput,
  SendMessageResult,
  WebAgentApiAdapter,
} from "./types";
import type { Message, Session, Skill, SkillKey } from "@/types";
import {
  mockArtifacts,
  mockMessages,
  mockModels,
  mockSessions,
  mockSkills,
  mockUser,
} from "../mock-data";

let sessions: Session[] = [...mockSessions];
let messages: Message[] = [...mockMessages];

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
}

function getSkillName(skills: Skill[], skillKey?: SkillKey) {
  if (!skillKey) {
    return "Auto";
  }

  return skills.find((skill) => skill.key === skillKey)?.name ?? "Skill";
}

export const mockAdapter: WebAgentApiAdapter = {
  async createSession(input: CreateSessionInput) {
    const now = new Date().toISOString();
    const skillName = getSkillName(mockSkills, input.skillKey);
    const session: Session = {
      id: createId("session"),
      title:
        input.title ??
        (input.skillKey ? `${skillName} session` : "New conversation"),
      type: input.skillKey ?? "chat",
      pinned: false,
      status: "active",
      updatedAt: now,
    };

    sessions = [session, ...sessions];

    return session;
  },
  async getCurrentUser() {
    return mockUser;
  },
  async listArtifacts(sessionId?: string) {
    return sessionId
      ? mockArtifacts.filter((artifact) => artifact.sessionId === sessionId)
      : mockArtifacts;
  },
  async listMessages(sessionId?: string) {
    return sessionId
      ? messages.filter((message) => message.sessionId === sessionId)
      : messages;
  },
  async listModels() {
    return mockModels;
  },
  async listSessions() {
    return sessions;
  },
  async listSkills() {
    return mockSkills;
  },
  async sendMessage(input: SendMessageInput): Promise<SendMessageResult> {
    const now = new Date().toISOString();
    const skillName = getSkillName(mockSkills, input.skillKey);
    const userMessage: Message = {
      id: createId("message_user"),
      sessionId: input.sessionId,
      role: "user",
      content: input.content.trim(),
      createdAt: now,
    };
    const assistantMessage: Message = {
      id: createId("message_assistant"),
      sessionId: input.sessionId,
      role: "assistant",
      content: input.skillKey
        ? `Entered ${skillName} mode. A real Agent run will be connected in the next backend phase.`
        : "This is a mock response. FastAPI, SSE, and the Agent runtime will be connected later.",
      createdAt: now,
    };

    messages = [...messages, userMessage, assistantMessage];
    sessions = sessions.map((session) =>
      session.id === input.sessionId
        ? { ...session, status: "active", updatedAt: now }
        : session,
    );

    const session = sessions.find((item) => item.id === input.sessionId);

    if (!session) {
      throw new Error("Session not found");
    }

    return {
      messages: [userMessage, assistantMessage],
      session,
    };
  },
};

