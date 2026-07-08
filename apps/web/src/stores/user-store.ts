"use client";

import { create } from "zustand";
import { settingsApi, webAgentApi } from "@/services";
import type { User } from "@/types";

interface UserState {
  error?: string;
  hydrated: boolean;
  saving: boolean;
  savedAt?: string;
  user?: User;
  hydrate: () => Promise<void>;
  updateProfile: (input: Pick<User, "nickname" | "email" | "avatarUrl">) => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  error: undefined,
  hydrated: false,
  saving: false,
  savedAt: undefined,
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
  updateProfile: async (input) => {
    set({ error: undefined, saving: true });
    try {
      const user = await settingsApi.updateProfile(input);

      set({
        savedAt: new Date().toISOString(),
        saving: false,
        user,
      });
    } catch (error) {
      set({
        error:
          error instanceof Error ? error.message : "Failed to save profile.",
        saving: false,
      });
    }
  },
}));
