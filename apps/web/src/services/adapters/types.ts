import type {
  Artifact,
  Message,
  ModelConfig,
  Session,
  Skill,
  SkillKey,
  User,
} from "@/types";

export interface CreateSessionInput {
  skillKey?: SkillKey;
  title?: string;
}

export interface SendMessageInput {
  content: string;
  sessionId: string;
  skillKey?: SkillKey;
}

export interface SendMessageResult {
  messages: Message[];
  session: Session;
}

export interface WebAgentApiAdapter {
  createSession(input: CreateSessionInput): Promise<Session>;
  getCurrentUser(): Promise<User>;
  listArtifacts(sessionId?: string): Promise<Artifact[]>;
  listMessages(sessionId?: string): Promise<Message[]>;
  listModels(): Promise<ModelConfig[]>;
  listSessions(): Promise<Session[]>;
  listSkills(): Promise<Skill[]>;
  sendMessage(input: SendMessageInput): Promise<SendMessageResult>;
}

