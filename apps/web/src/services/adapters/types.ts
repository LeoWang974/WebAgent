/**
 * File purpose: Implements browser-side API access for types.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

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
import type { SessionVisibility } from "@/types/session";

export interface CreateSessionInput {
  folderId?: string;
  title?: string;
}

export interface LoginInput {
  email?: string;
  identifier?: string;
  password: string;
  username?: string;
}

export interface RegisterInput extends LoginInput {
  email?: string;
  nickname?: string;
  username?: string;
}

export interface AdminUserCreateInput {
  email: string;
  nickname?: string;
  password: string;
  role: "admin" | "user";
  username?: string;
}

export interface AuthResult {
  accessToken: string;
  user: User;
}

export interface SendMessageInput {
  content: string;
  modelId?: string;
  signal?: AbortSignal;
  sessionId: string;
}

export type SendMessageStreamEvent =
  | {
      message: Message;
      type: "user_message";
    }
  | {
      progress: number;
      queueName?: string;
      queuePosition?: number;
      queueReason?: string;
      runId: string;
      sessionId: string;
      status: AgentRun["status"];
      type: "run_started";
    }
  | {
      content: string;
      messageId: string;
      runId?: string;
      sessionId: string;
      type: "assistant_delta";
    }
  | {
      message: Message;
      runId?: string;
      session: Session;
      status?: AgentRun["status"];
      type: "assistant_done";
    }
  | {
      artifact: Artifact;
      messageId: string;
      runId?: string;
      sessionId: string;
      type: "artifact_created";
    };

export type SendMessageStreamHandler = (event: SendMessageStreamEvent) => void;

export interface UpdateSessionInput {
  folderId?: string | null;
  pinned?: boolean;
  shareWithEmail?: string;
  title?: string;
  unshareUserId?: string;
  visibility?: SessionVisibility;
}

export interface UploadFileInput {
  file: File;
  sessionId?: string;
}

export type AgentRunEventHandler = (event: AgentRunEvent) => void;

export type AgentRunUnsubscribe = () => void;

export interface WebAgentApiAdapter {
  cancelAgentRun(runId: string): Promise<AgentRun>;
  createConversationFolder(name: string): Promise<ConversationFolder>;
  createSession(input: CreateSessionInput): Promise<Session>;
  createUser(input: AdminUserCreateInput): Promise<User>;
  deleteArtifact(artifactId: string): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
  deleteConversationFolder(folderId: string): Promise<void>;
  deleteUser(userId: string): Promise<void>;
  downloadArtifact(artifactId: string): Promise<Blob>;
  getCurrentUser(): Promise<User>;
  getArtifact(artifactId: string): Promise<Artifact>;
  getArtifactSlides(artifactId: string): Promise<ArtifactSlides>;
  getAgentRun(runId: string): Promise<AgentRun>;
  login(input: LoginInput): Promise<AuthResult>;
  logout(): Promise<void>;
  listArtifacts(sessionId?: string, runId?: string): Promise<Artifact[]>;
  listAgentRuns(sessionId?: string): Promise<AgentRun[]>;
  listFiles(sessionId?: string): Promise<FileAsset[]>;
  listConversationFolders(): Promise<ConversationFolder[]>;
  listMessages(sessionId?: string): Promise<Message[]>;
  listModels(): Promise<ModelConfig[]>;
  listSessions(): Promise<Session[]>;
  listSkills(): Promise<Skill[]>;
  listUsers(): Promise<User[]>;
  register(input: RegisterInput): Promise<AuthResult>;
  resetUserPassword(userId: string, newPassword: string): Promise<User>;
  sendMessageStream(
    input: SendMessageInput,
    onEvent: SendMessageStreamHandler,
  ): Promise<void>;
  subscribeAgentRun(
    runId: string,
    onEvent: AgentRunEventHandler,
  ): AgentRunUnsubscribe;
  updateSession(sessionId: string, input: UpdateSessionInput): Promise<Session>;
  uploadFile(input: UploadFileInput): Promise<FileAsset>;
}
