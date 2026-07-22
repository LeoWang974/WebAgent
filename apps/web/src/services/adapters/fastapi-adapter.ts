import { apiClient, getAccessToken } from "../api-client";
import { parseSseEvents, parseSseJson, splitSseBuffer } from "../sse-parser";
import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  ArtifactSlides,
  FileAsset,
  Message,
  ModelConfig,
  ConversationFolder,
  Session,
  Skill,
  User,
} from "@/types";
import type {
  AdminUserCreateInput,
  AuthResult,
  CreateAgentRunInput,
  CreateSessionInput,
  LoginInput,
  RegisterInput,
  SendMessageInput,
  SendMessageResult,
  SendMessageStreamHandler,
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
        folder_id: input.folderId,
        skill_key: input.skillKey,
        title: input.title,
      }),
      method: "POST",
    });
  },
  createConversationFolder(name: string) {
    return apiClient<ConversationFolder>("/api/sessions/folders", {
      body: JSON.stringify({ name }),
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
  createUser(input: AdminUserCreateInput) {
    return apiClient<User>("/api/admin/users", {
      body: JSON.stringify(input),
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
  deleteConversationFolder(folderId: string) {
    return apiClient<void>(`/api/sessions/folders/${folderId}`, {
      method: "DELETE",
    });
  },
  deleteUser(userId: string) {
    return apiClient<void>(`/api/admin/users/${userId}`, {
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
  getArtifactSlides(artifactId: string) {
    return apiClient<ArtifactSlides>(`/api/artifacts/${artifactId}/slides`);
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
  listAgentRuns(sessionId?: string) {
    const path = sessionId
      ? `/api/agent-runs?session_id=${encodeURIComponent(sessionId)}`
      : "/api/agent-runs";
    return apiClient<AgentRun[]>(path);
  },
  listFiles(sessionId?: string) {
    const path = sessionId ? `/api/sessions/${sessionId}/files` : "/api/files";
    return apiClient<FileAsset[]>(path);
  },
  listConversationFolders() {
    return apiClient<ConversationFolder[]>("/api/sessions/folders");
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
  listUsers() {
    return apiClient<User[]>("/api/admin/users");
  },
  async register(input: RegisterInput) {
    const result = await apiClient<AuthResult>("/api/auth/register", {
      body: JSON.stringify(input),
      method: "POST",
    });

    return persistAuth(result);
  },
  resetUserPassword(userId: string, newPassword: string) {
    return apiClient<User>(`/api/admin/users/${userId}/password`, {
      body: JSON.stringify({ newPassword }),
      method: "POST",
    });
  },
  sendMessage(input: SendMessageInput) {
    return apiClient<SendMessageResult>(
      `/api/sessions/${input.sessionId}/messages`,
      {
        body: JSON.stringify({
          content: input.content,
          model_id: input.modelId,
          skill_key: input.skillKey,
        }),
        method: "POST",
        signal: input.signal,
      },
    );
  },
  async sendMessageStream(
    input: SendMessageInput,
    onEvent: SendMessageStreamHandler,
  ) {
    const response = await fetch(
      `${API_BASE_URL}/api/sessions/${input.sessionId}/messages/stream`,
      {
        body: JSON.stringify({
          content: input.content,
          model_id: input.modelId,
          skill_key: input.skillKey,
        }),
        headers: {
          "Content-Type": "application/json",
          ...(typeof window !== "undefined" && window.localStorage.getItem("webagent_access_token")
            ? { Authorization: `Bearer ${window.localStorage.getItem("webagent_access_token")}` }
            : {}),
        },
        method: "POST",
        signal: input.signal,
      },
    );

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Streaming response is not available.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const { events, remainingBuffer } = splitSseBuffer(buffer);
      buffer = remainingBuffer;

      for (const event of events) {
        onEvent({
          ...event.data,
          type: event.type,
        } as Parameters<SendMessageStreamHandler>[0]);
      }
    }

    if (buffer.trim()) {
      for (const event of parseSseEvents(buffer)) {
        onEvent({
          ...event.data,
          type: event.type,
        } as Parameters<SendMessageStreamHandler>[0]);
      }
    }
  },
  subscribeAgentRun(runId, onEvent) {
    let reconnectTimer: number | undefined;
    let source: EventSource | undefined;
    let stopped = false;

    const connect = () => {
      const token = getAccessToken();
      const searchParams = new URLSearchParams();
      if (token) {
        searchParams.set("access_token", token);
      }
      const query = searchParams.toString();
      source = new EventSource(
        `${API_BASE_URL}/api/agent-runs/${runId}/events${query ? `?${query}` : ""}`,
      );

      source.onmessage = (message) => {
        const event = parseSseJson<AgentRunEvent>(message.data, "message");
        if (event) {
          onEvent(event);
        }
      };

      source.addEventListener("agent_run_event", (message) => {
        const event = parseSseJson<AgentRunEvent>(message.data, "agent_run_event");
        if (event) {
          onEvent(event);
        }
      });

      source.onerror = () => {
        source?.close();
        source = undefined;
        if (!stopped) {
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      source?.close();
    };
  },
  updateSession(sessionId: string, input: UpdateSessionInput) {
    return apiClient<Session>(`/api/sessions/${sessionId}`, {
      body: JSON.stringify({
        folder_id: input.folderId,
        pinned: input.pinned,
        share_with_email: input.shareWithEmail,
        title: input.title,
        unshare_user_id: input.unshareUserId,
        visibility: input.visibility,
      }),
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
