import { apiClient } from "../api-client";
import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  FileAsset,
  Message,
  ModelConfig,
  Session,
  Skill,
  User,
} from "@/types";
import type {
  AuthResult,
  CreateAgentRunInput,
  CreateSessionInput,
  LoginInput,
  SendMessageInput,
  SendMessageResult,
  UpdateSessionInput,
  UploadFileInput,
  WebAgentApiAdapter,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function persistAuth(result: AuthResult) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem("webagent_access_token", result.accessToken);
  }

  return result;
}

export const fastApiAdapter: WebAgentApiAdapter = {
  cancelAgentRun(runId: string) {
    return apiClient<AgentRun>(`/api/agent-runs/${runId}/cancel`, {
      method: "POST",
    });
  },
  createSession(input: CreateSessionInput) {
    return apiClient<Session>("/api/sessions", {
      body: JSON.stringify({
        skill_key: input.skillKey,
        title: input.title,
      }),
      method: "POST",
    });
  },
  createAgentRun(input: CreateAgentRunInput) {
    return apiClient<AgentRun>("/api/agent-runs", {
      body: JSON.stringify({
        content: input.content,
        model_id: input.modelId,
        session_id: input.sessionId,
        skill_key: input.skillKey,
      }),
      method: "POST",
    });
  },
  deleteArtifact(artifactId: string) {
    return apiClient<void>(`/api/artifacts/${artifactId}`, {
      method: "DELETE",
    });
  },
  deleteSession(sessionId: string) {
    return apiClient<void>(`/api/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },
  downloadArtifact(artifactId: string) {
    return apiClient<Blob>(`/api/artifacts/${artifactId}/download`);
  },
  getCurrentUser() {
    return apiClient<User>("/api/auth/me");
  },
  getAgentRun(runId: string) {
    return apiClient<AgentRun>(`/api/agent-runs/${runId}`);
  },
  getArtifact(artifactId: string) {
    return apiClient<Artifact>(`/api/artifacts/${artifactId}`);
  },
  async login(input: LoginInput) {
    const result = await apiClient<AuthResult>("/api/auth/login", {
      body: JSON.stringify(input),
      method: "POST",
    });

    return persistAuth(result);
  },
  logout() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("webagent_access_token");
    }

    return apiClient<void>("/api/auth/logout", {
      method: "POST",
    });
  },
  listArtifacts(sessionId?: string) {
    const path = sessionId
      ? `/api/sessions/${sessionId}/artifacts`
      : "/api/artifacts";
    return apiClient<Artifact[]>(path);
  },
  listFiles(sessionId?: string) {
    const path = sessionId ? `/api/sessions/${sessionId}/files` : "/api/files";
    return apiClient<FileAsset[]>(path);
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
  async register(input: LoginInput) {
    const result = await apiClient<AuthResult>("/api/auth/register", {
      body: JSON.stringify(input),
      method: "POST",
    });

    return persistAuth(result);
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
  subscribeAgentRun(runId, onEvent) {
    const source = new EventSource(
      `${API_BASE_URL}/api/agent-runs/${runId}/events`,
    );

    source.onmessage = (message) => {
      onEvent(JSON.parse(message.data) as AgentRunEvent);
    };

    source.addEventListener("agent_run_event", (message) => {
      onEvent(JSON.parse(message.data) as AgentRunEvent);
    });

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  },
  updateSession(sessionId: string, input: UpdateSessionInput) {
    return apiClient<Session>(`/api/sessions/${sessionId}`, {
      body: JSON.stringify(input),
      method: "PATCH",
    });
  },
  uploadFile(input: UploadFileInput) {
    const formData = new FormData();
    formData.append("file", input.file);

    if (input.sessionId) {
      formData.append("session_id", input.sessionId);
    }

    return apiClient<FileAsset>("/api/files", {
      body: formData,
      method: "POST",
    });
  },
};
