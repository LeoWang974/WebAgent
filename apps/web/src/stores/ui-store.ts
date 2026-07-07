"use client";

import { create } from "zustand";

interface UiState {
  artifactDrawerOpen: boolean;
  sessionSearchQuery: string;
  sidebarCollapsed: boolean;
  closeArtifactDrawer: () => void;
  openArtifactDrawer: () => void;
  setSessionSearchQuery: (value: string) => void;
  setSidebarCollapsed: (value: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  artifactDrawerOpen: false,
  sessionSearchQuery: "",
  sidebarCollapsed: false,
  closeArtifactDrawer: () => set({ artifactDrawerOpen: false }),
  openArtifactDrawer: () => set({ artifactDrawerOpen: true }),
  setSessionSearchQuery: (value) => set({ sessionSearchQuery: value }),
  setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
}));
