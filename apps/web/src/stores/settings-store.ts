"use client";

import { create } from "zustand";
import { settingsApi } from "@/services";
import type { DataContextSettings } from "@/types";

interface SettingsState {
  dataContextSettings?: DataContextSettings;
  error?: string;
  hydrated: boolean;
  saving: boolean;
  savedAt?: string;
  hydrate: () => Promise<void>;
  reset: () => void;
  updateDataContextSettings: (input: DataContextSettings) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  dataContextSettings: undefined,
  error: undefined,
  hydrated: false,
  saving: false,
  savedAt: undefined,
  hydrate: async () => {
    if (get().hydrated) {
      return;
    }

    try {
      const dataContextSettings = await settingsApi.getDataContextSettings();
      set({ dataContextSettings, hydrated: true });
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to load data settings.",
        hydrated: true,
      });
    }
  },
  reset: () => {
    set({
      dataContextSettings: undefined,
      error: undefined,
      hydrated: false,
      saving: false,
      savedAt: undefined,
    });
  },
  updateDataContextSettings: async (input) => {
    set({ error: undefined, saving: true });

    try {
      const dataContextSettings =
        await settingsApi.updateDataContextSettings(input);
      set({
        dataContextSettings,
        savedAt: new Date().toISOString(),
        saving: false,
      });
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to save data settings.",
        saving: false,
      });
    }
  },
}));
