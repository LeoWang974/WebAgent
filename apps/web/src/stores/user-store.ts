"use client";

import { create } from "zustand";
import type { User } from "@/types";
import { mockUser } from "@/services/mock-data";

interface UserState {
  user: User;
}

export const useUserStore = create<UserState>(() => ({
  user: mockUser,
}));

