/**
 * File purpose: Defines shared TypeScript contracts for message.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface Message {
  id: string;
  sessionId: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  artifactIds?: string[];
  isPending?: boolean;
  pendingLabel?: string;
  waitStartedAt?: string;
}
