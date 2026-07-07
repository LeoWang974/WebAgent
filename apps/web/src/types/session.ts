import type { SkillKey } from "./skill";

export type SessionStatus = "active" | "running" | "failed" | "completed";

export interface Session {
  id: string;
  title: string;
  type: "chat" | SkillKey;
  pinned: boolean;
  status: SessionStatus;
  updatedAt: string;
}

