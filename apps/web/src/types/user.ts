export interface User {
  id: string;
  nickname: string;
  email: string;
  avatarUrl?: string;
  role?: "admin" | "user";
}
