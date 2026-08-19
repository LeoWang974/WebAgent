/**
 * File purpose: Defines shared TypeScript contracts for user.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

export interface User {
  id: string;
  nickname: string;
  email: string;
  username?: string;
  passwordMask?: string;
  conversationCount?: number;
  createdAt?: string;
  updatedAt?: string;
  avatarUrl?: string;
  role?: "admin" | "user";
}
