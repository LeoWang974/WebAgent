"use client";

import { create } from "zustand";
import { ApiError } from "@/services/api-client";
import { settingsApi, webAgentApi } from "@/services";
import type { User } from "@/types";

interface UserState {
  error?: string;
  hydrated: boolean;
  saving: boolean;
  savedAt?: string;
  user?: User;
  hydrate: () => Promise<void>;
  login: (input: { email: string; password: string }) => Promise<boolean>;
  logout: () => Promise<void>;
  register: (input: { email: string; nickname?: string; password: string }) => Promise<boolean>;
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
      if (error instanceof ApiError && error.status === 401) {
        set({ hydrated: true, user: undefined });
        return;
      }

      set({
        error:
          error instanceof Error ? error.message : "Failed to load user data.",
        hydrated: true,
      });
    }
  },
  login: async (input) => {
    set({ error: undefined, saving: true });
    try {
      const result = await webAgentApi.login(input);
      set({ hydrated: true, saving: false, user: result.user });
      return true;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to log in.",
        saving: false,
      });
      return false;
    }
  },
  logout: async () => {
    set({ error: undefined, saving: true });
    try {
      await webAgentApi.logout();
    } finally {
      set({ hydrated: true, saving: false, user: undefined });
    }
  },
  register: async (input) => {
    set({ error: undefined, saving: true });
    try {
      const result = await webAgentApi.register(input);
      set({ hydrated: true, saving: false, user: result.user });
      return true;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Failed to register.",
        saving: false,
      });
      return false;
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
