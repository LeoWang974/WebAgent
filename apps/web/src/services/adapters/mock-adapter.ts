import type {
  AdminUserCreateInput,
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
import type {
  AgentRun,
  Artifact,
  ArtifactSlides,
  ConversationFolder,
  FileAsset,
  Message,
  Session,
  User,
} from "@/types";
import {
  mockArtifacts,
  mockMessages,
  mockModels,
  mockSessions,
  mockSkills,
  mockUser,
} from "../mock-data";

// DEV-ONLY: mock adapter for isolated UI work.
// Set NEXT_PUBLIC_API_ADAPTER=mock explicitly to use this path.
let sessions: Session[] = [...mockSessions];
let messages: Message[] = [...mockMessages];
let artifacts: Artifact[] = [...mockArtifacts];
let files: FileAsset[] = [];
let folders: ConversationFolder[] = [];
let runs: AgentRun[] = [];
let users: User[] = [{ ...mockUser, passwordMask: "********", role: "admin" }];

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
}

export const mockAdapter: WebAgentApiAdapter = {
  async cancelAgentRun(runId: string) {
    const run = runs.find((item) => item.id === runId);

    if (!run) {
      throw new Error("Agent run not found");
    }

    const updatedRun: AgentRun = {
      ...run,
      completedAt: new Date().toISOString(),
      progress: run.progress,
      status: "cancelled",
    };

    runs = runs.map((item) => (item.id === runId ? updatedRun : item));

    return updatedRun;
  },
  async createSession(input: CreateSessionInput) {
    const now = new Date().toISOString();
    const session: Session = {
      id: createId("session"),
      folderId: input.folderId,
      title: input.title ?? "New conversation",
      type: "chat",
      pinned: false,
      status: "active",
      updatedAt: now,
    };

    sessions = [session, ...sessions];

    return session;
  },
  async createConversationFolder(name: string) {
    const now = new Date().toISOString();
    const folder: ConversationFolder = {
      createdAt: now,
      id: createId("folder"),
      name,
      updatedAt: now,
    };
    folders = [...folders, folder];
    return folder;
  },
  async createUser(input: AdminUserCreateInput) {
    const user: User = {
      email: input.email,
      id: createId("user"),
      nickname: input.nickname || input.email.split("@")[0],
      passwordMask: "********",
      role: input.role,
      username: input.username,
    };
    users = [user, ...users];
    return user;
  },
  async deleteArtifact(artifactId: string) {
    artifacts = artifacts.filter((artifact) => artifact.id !== artifactId);
  },
  async deleteSession(sessionId: string) {
    sessions = sessions.filter((session) => session.id !== sessionId);
    messages = messages.filter((message) => message.sessionId !== sessionId);
    artifacts = artifacts.filter((artifact) => artifact.sessionId !== sessionId);
  },
  async deleteConversationFolder(folderId: string) {
    folders = folders.filter((folder) => folder.id !== folderId);
    sessions = sessions.map((session) =>
      session.folderId === folderId ? { ...session, folderId: undefined } : session,
    );
  },
  async deleteUser(userId: string) {
    users = users.filter((user) => user.id !== userId);
  },
  async downloadArtifact(artifactId: string) {
    const artifact = artifacts.find((item) => item.id === artifactId);

    if (!artifact) {
      throw new Error("Artifact not found");
    }

    return new Blob([artifact.content ?? artifact.title], {
      type: "text/plain;charset=utf-8",
    });
  },
  async getCurrentUser() {
    return mockUser;
  },
  async getAgentRun(runId: string) {
    const run = runs.find((item) => item.id === runId);

    if (!run) {
      throw new Error("Agent run not found");
    }

    return run;
  },
  async getArtifact(artifactId: string) {
    const artifact = artifacts.find((item) => item.id === artifactId);

    if (!artifact) {
      throw new Error("Artifact not found");
    }

    return artifact;
  },
  async getArtifactSlides(artifactId: string): Promise<ArtifactSlides> {
    const artifact = artifacts.find((item) => item.id === artifactId);
    const slides = Array.isArray(artifact?.metadata?.slides)
      ? artifact.metadata.slides.map((slide, index) => ({
          content: `<section style="font-family: system-ui; height: 100vh; padding: 56px; box-sizing: border-box;"><h1>${String((slide as { title?: string }).title ?? `Slide ${index + 1}`)}</h1></section>`,
          contentType: "text/html",
          id: `${artifactId}_${index + 1}`,
          index: index + 1,
          title: String((slide as { title?: string }).title ?? `Slide ${index + 1}`),
        }))
      : [];
    return { artifactId, slides, source: "mock" };
  },
  async login(input: LoginInput) {
    return {
      accessToken: `mock_token_${input.identifier ?? input.username ?? input.email}`,
      user: { ...mockUser, email: input.email ?? mockUser.email, username: input.username ?? input.identifier },
    };
  },
  async logout() {
    return undefined;
  },
  async listArtifacts(sessionId?: string) {
    return sessionId
      ? artifacts.filter((artifact) => artifact.sessionId === sessionId)
      : artifacts;
  },
  async listAgentRuns(sessionId?: string) {
    return sessionId ? runs.filter((run) => run.sessionId === sessionId) : runs;
  },
  async listFiles(sessionId?: string) {
    return sessionId
      ? files.filter((file) => file.sessionId === sessionId)
      : files;
  },
  async listConversationFolders() {
    return folders;
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
  async listUsers() {
    return users;
  },
  async register(input: RegisterInput) {
    const username = input.username || input.email?.split("@")[0] || "user";
    const email = input.email || `${username}@webagent.local`;
    return {
      accessToken: `mock_token_${email}`,
      user: { ...mockUser, email, username },
    };
  },
  async resetUserPassword(userId: string) {
    const user = users.find((item) => item.id === userId);
    if (!user) {
      throw new Error("User not found");
    }
    const updatedUser = { ...user, passwordMask: "********" };
    users = users.map((item) => (item.id === userId ? updatedUser : item));
    return updatedUser;
  },
  async sendMessage(input: SendMessageInput): Promise<SendMessageResult> {
    const now = new Date().toISOString();
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
      content: "This is a mock Hermes response. Set NEXT_PUBLIC_API_ADAPTER=fastapi to use the backend.",
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
  async sendMessageStream(
    input: SendMessageInput,
    onEvent: SendMessageStreamHandler,
  ) {
    const result = await this.sendMessage(input);
    const userMessage = result.messages.find((message) => message.role === "user");
    const assistantMessage = result.messages.find(
      (message) => message.role === "assistant",
    );

    if (userMessage) {
      onEvent({ message: userMessage, type: "user_message" });
    }

    if (assistantMessage) {
      onEvent({
        content: assistantMessage.content,
        messageId: assistantMessage.id,
        sessionId: assistantMessage.sessionId,
        type: "assistant_delta",
      });
      onEvent({
        message: assistantMessage,
        session: result.session,
        type: "assistant_done",
      });
    }
  },
  subscribeAgentRun(runId, onEvent) {
    const steps = [
      { label: "Queued request", progress: 12, status: "queued" as const },
      { label: "Selected skill and model", progress: 32, status: "running" as const },
      { label: "Calling agent tools", progress: 58, status: "tool_calling" as const },
      { label: "Preparing artifact preview", progress: 82, status: "rendering" as const },
      { label: "Completed response", progress: 100, status: "completed" as const },
    ];
    const timers = steps.map((step, index) =>
      window.setTimeout(() => {
        const now = new Date().toISOString();
        onEvent({
          completedAt: step.status === "completed" ? now : undefined,
          eventType: step.status === "completed" ? "completed" : "stage_update",
          progress: step.progress,
          runId,
          status: step.status,
          step: {
            id: `${runId}_step_${index}`,
            label: step.label,
            status: step.status === "completed" ? "completed" : "running",
            timestamp: now,
          },
        });
      }, 300 + index * 450),
    );

    return () => timers.forEach((timer) => window.clearTimeout(timer));
  },
  async updateSession(sessionId: string, input: UpdateSessionInput) {
    const session = sessions.find((item) => item.id === sessionId);

    if (!session) {
      throw new Error("Session not found");
    }

    const updatedSession: Session = {
      ...session,
      folderId: input.folderId === null ? undefined : input.folderId ?? session.folderId,
      pinned: input.pinned ?? session.pinned,
      title: input.title ?? session.title,
      visibility: input.visibility ?? session.visibility,
      sharedWith: input.shareWithEmail
        ? [
            ...(session.sharedWith ?? []),
            {
              email: input.shareWithEmail,
              id: createId("shared_user"),
              nickname: input.shareWithEmail.split("@")[0],
              role: "viewer",
            },
          ]
        : input.unshareUserId
          ? session.sharedWith?.filter((share) => share.id !== input.unshareUserId)
          : session.sharedWith,
      updatedAt: new Date().toISOString(),
    };

    sessions = sessions.map((item) =>
      item.id === sessionId ? updatedSession : item,
    );

    return updatedSession;
  },
  async uploadFile(input: UploadFileInput) {
    const fileAsset: FileAsset = {
      contentType: input.file.type || "application/octet-stream",
      createdAt: new Date().toISOString(),
      filename: input.file.name,
      id: createId("file"),
      sessionId: input.sessionId,
      size: input.file.size,
    };

    files = [fileAsset, ...files];

    return fileAsset;
  },
};
