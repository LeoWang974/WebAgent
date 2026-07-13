import type {
  AgentRun,
  AgentRunEvent,
  Artifact,
  FileAsset,
  Message,
  ModelConfig,
  Session,
  Skill,
  SkillKey,
  User,
} from "@/types";
import type { SessionVisibility } from "@/types/session";

export interface CreateSessionInput {
  skillKey?: SkillKey;
  title?: string;
}

export interface LoginInput {
  email: string;
  password: string;
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
  skillKey?: SkillKey;
}

export interface SendMessageResult {
  messages: Message[];
  session: Session;
}

export type SendMessageStreamEvent =
  | {
      message: Message;
      type: "user_message";
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
  pinned?: boolean;
  shareWithEmail?: string;
  title?: string;
  unshareUserId?: string;
  visibility?: SessionVisibility;
}

export interface CreateAgentRunInput {
  content: string;
  modelId?: string;
  sessionId: string;
  skillKey?: SkillKey;
}

export interface UploadFileInput {
  file: File;
  sessionId?: string;
}

export type AgentRunEventHandler = (event: AgentRunEvent) => void;

export type AgentRunUnsubscribe = () => void;

export interface WebAgentApiAdapter {
  cancelAgentRun(runId: string): Promise<AgentRun>;
  createSession(input: CreateSessionInput): Promise<Session>;
  createAgentRun(input: CreateAgentRunInput): Promise<AgentRun>;
  deleteArtifact(artifactId: string): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
  downloadArtifact(artifactId: string): Promise<Blob>;
  getCurrentUser(): Promise<User>;
  getArtifact(artifactId: string): Promise<Artifact>;
  getAgentRun(runId: string): Promise<AgentRun>;
  login(input: LoginInput): Promise<AuthResult>;
  logout(): Promise<void>;
  listArtifacts(sessionId?: string): Promise<Artifact[]>;
  listFiles(sessionId?: string): Promise<FileAsset[]>;
  listMessages(sessionId?: string): Promise<Message[]>;
  listModels(): Promise<ModelConfig[]>;
  listSessions(): Promise<Session[]>;
  listSkills(): Promise<Skill[]>;
  register(input: LoginInput): Promise<AuthResult>;
  sendMessage(input: SendMessageInput): Promise<SendMessageResult>;
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
