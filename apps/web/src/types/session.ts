import type { SkillKey } from "./skill";

export type SessionStatus = "active" | "running" | "failed" | "completed";
export type SessionVisibility = "private" | "shared" | "public";

export interface SessionShare {
  id: string;
  email: string;
  nickname: string;
  role: string;
}

export interface Session {
  id: string;
  title: string;
  type: "chat" | SkillKey;
  pinned: boolean;
  status: SessionStatus;
  updatedAt: string;
  ownerId?: string;
  sharedWith?: SessionShare[];
  visibility?: SessionVisibility;
}
