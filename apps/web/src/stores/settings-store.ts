"use client";

import { create } from "zustand";
import { settingsApi } from "@/services";
import type { DataContextSettings, InterfaceSettings } from "@/types";

interface SettingsState {
  dataContextSettings?: DataContextSettings;
  error?: string;
  hydrated: boolean;
  saving: boolean;
  savedAt?: string;
  interfaceSettings?: InterfaceSettings;
  hydrate: () => Promise<void>;
  reset: () => void;
  updateDataContextSettings: (input: DataContextSettings) => Promise<void>;
  updateInterfaceSettings: (input: InterfaceSettings) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  dataContextSettings: undefined,
  error: undefined,
  hydrated: false,
  saving: false,
  savedAt: undefined,
  interfaceSettings: undefined,
  hydrate: async () => {
    if (get().hydrated) {
      return;
    }

    try {
      const [dataContextSettings, interfaceSettings] = await Promise.all([
        settingsApi.getDataContextSettings(),
        settingsApi.getInterfaceSettings(),
      ]);
      set({ dataContextSettings, hydrated: true, interfaceSettings });
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
      interfaceSettings: undefined,
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
  updateInterfaceSettings: async (input) => {
    const previousSettings = get().interfaceSettings;
    set({ error: undefined, saving: true });

    try {
      set({ interfaceSettings: input });
      const interfaceSettings = await settingsApi.updateInterfaceSettings(input);
      set({
        interfaceSettings,
        savedAt: new Date().toISOString(),
        saving: false,
      });
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to save interface settings.",
        interfaceSettings: previousSettings,
        saving: false,
      });
    }
  },
}));
