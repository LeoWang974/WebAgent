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
