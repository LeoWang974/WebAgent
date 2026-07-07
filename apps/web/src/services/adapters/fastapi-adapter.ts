import { apiClient } from "../api-client";
import type {
  Artifact,
  Message,
  ModelConfig,
  Session,
  Skill,
  User,
} from "@/types";
import type {
  CreateSessionInput,
  SendMessageInput,
  SendMessageResult,
  WebAgentApiAdapter,
} from "./types";

export const fastApiAdapter: WebAgentApiAdapter = {
  createSession(input: CreateSessionInput) {
    return apiClient<Session>("/api/sessions", {
      body: JSON.stringify({
        skill_key: input.skillKey,
        title: input.title,
      }),
      method: "POST",
    });
  },
  getCurrentUser() {
    return apiClient<User>("/api/auth/me");
  },
  listArtifacts(sessionId?: string) {
    const path = sessionId
      ? `/api/sessions/${sessionId}/artifacts`
      : "/api/artifacts";
    return apiClient<Artifact[]>(path);
  },
  listMessages(sessionId?: string) {
    const path = sessionId
      ? `/api/sessions/${sessionId}/messages`
      : "/api/messages";
    return apiClient<Message[]>(path);
  },
  listModels() {
    return apiClient<ModelConfig[]>("/api/models");
  },
  listSessions() {
    return apiClient<Session[]>("/api/sessions");
  },
  listSkills() {
    return apiClient<Skill[]>("/api/skills");
  },
  sendMessage(input: SendMessageInput) {
    return apiClient<SendMessageResult>(
      `/api/sessions/${input.sessionId}/messages`,
      {
        body: JSON.stringify({
          content: input.content,
          skill_key: input.skillKey,
        }),
        method: "POST",
      },
    );
  },
};

