"use client";

import { create } from "zustand";
import { webAgentApi } from "@/services";
import type { User } from "@/types";

interface UserState {
  error?: string;
  hydrated: boolean;
  user?: User;
  hydrate: () => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  error: undefined,
  hydrated: false,
  user: undefined,
  hydrate: async () => {
    if (get().hydrated) {
      return;
    }

    try {
      const user = await webAgentApi.getCurrentUser();
      set({ hydrated: true, user });
    } catch (error) {
      set({
        error:
          error instanceof Error ? error.message : "Failed to load user data.",
        hydrated: true,
      });
    }
  },
}));

