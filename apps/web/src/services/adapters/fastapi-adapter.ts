import { API_BASE_URL, apiClient, getAccessToken } from "../api-client";
import { parseSseEvents, splitSseBuffer } from "../sse-parser";
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
        adapter_key: input.adapterKey,
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
          adapter_key: input.adapterKey,
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
          adapter_key: input.adapterKey,
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
    let controller: AbortController | undefined;
    let stopped = false;

    const scheduleReconnect = () => {
      if (!stopped && reconnectTimer === undefined) {
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = undefined;
          void connect();
        }, 1500);
      }
    };

    const connect = async () => {
      const token = getAccessToken();
      controller = new AbortController();
      let terminalEventReceived = false;

      const dispatchEvents = (events: ReturnType<typeof parseSseEvents>) => {
        for (const event of events) {
          if (event.type !== "agent_run_event") {
            continue;
          }
          const agentRunEvent = event.data as unknown as AgentRunEvent;
          if (agentRunEvent.runId !== runId || typeof agentRunEvent.status !== "string") {
            continue;
          }
          onEvent(agentRunEvent);
          terminalEventReceived =
            terminalEventReceived ||
            ["cancelled", "completed", "disconnected", "failed"].includes(
              agentRunEvent.status,
            );
        }
      };

      try {
        const response = await fetch(`${API_BASE_URL}/api/agent-runs/${runId}/events`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error(`Agent run event stream failed: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const { events, remainingBuffer } = splitSseBuffer(buffer);
          buffer = remainingBuffer;
          dispatchEvents(events);
        }
        if (buffer.trim()) {
          dispatchEvents(parseSseEvents(buffer));
        }
      } catch (error) {
        if (stopped || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }
      } finally {
        controller = undefined;
      }

      if (!terminalEventReceived) {
        scheduleReconnect();
      }
    };

    void connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      controller?.abort();
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
