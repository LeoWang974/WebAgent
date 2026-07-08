"use client";

import { create } from "zustand";

export type AppLanguage = "zh-CN" | "en-US";

interface UiState {
  artifactDrawerOpen: boolean;
  artifactFullscreenOpen: boolean;
  artifactPanelOpen: boolean;
  artifactPanelWidth: number;
  language: AppLanguage;
  sidebarDrawerOpen: boolean;
  sessionSearchQuery: string;
  sidebarCollapsed: boolean;
  closeArtifactDrawer: () => void;
  closeArtifactFullscreen: () => void;
  closeSidebarDrawer: () => void;
  openArtifactDrawer: () => void;
  openArtifactFullscreen: () => void;
  openSidebarDrawer: () => void;
  setLanguage: (value: AppLanguage) => void;
  setArtifactPanelWidth: (value: number) => void;
  setSessionSearchQuery: (value: string) => void;
  setSidebarCollapsed: (value: boolean) => void;
  toggleArtifactPanel: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  artifactDrawerOpen: false,
  artifactFullscreenOpen: false,
  artifactPanelOpen: true,
  artifactPanelWidth: 420,
  language: "zh-CN",
  sidebarDrawerOpen: false,
  sessionSearchQuery: "",
  sidebarCollapsed: false,
  closeArtifactDrawer: () => set({ artifactDrawerOpen: false }),
  closeArtifactFullscreen: () => set({ artifactFullscreenOpen: false }),
  closeSidebarDrawer: () => set({ sidebarDrawerOpen: false }),
  openArtifactDrawer: () => set({ artifactDrawerOpen: true }),
  openArtifactFullscreen: () => set({ artifactFullscreenOpen: true }),
  openSidebarDrawer: () => set({ sidebarDrawerOpen: true }),
  setArtifactPanelWidth: (value) =>
    set({ artifactPanelWidth: Math.min(720, Math.max(320, value)) }),
  setLanguage: (value) => set({ language: value }),
  setSessionSearchQuery: (value) => set({ sessionSearchQuery: value }),
  setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
  toggleArtifactPanel: () =>
    set((state) => ({ artifactPanelOpen: !state.artifactPanelOpen })),
}));
