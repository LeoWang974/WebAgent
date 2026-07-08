"use client";

import { create } from "zustand";

export type AppLanguage = "zh-CN" | "en-US";

interface UiState {
  artifactDrawerOpen: boolean;
  language: AppLanguage;
  sidebarDrawerOpen: boolean;
  sessionSearchQuery: string;
  sidebarCollapsed: boolean;
  closeArtifactDrawer: () => void;
  closeSidebarDrawer: () => void;
  openArtifactDrawer: () => void;
  openSidebarDrawer: () => void;
  setLanguage: (value: AppLanguage) => void;
  setSessionSearchQuery: (value: string) => void;
  setSidebarCollapsed: (value: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  artifactDrawerOpen: false,
  language: "zh-CN",
  sidebarDrawerOpen: false,
  sessionSearchQuery: "",
  sidebarCollapsed: false,
  closeArtifactDrawer: () => set({ artifactDrawerOpen: false }),
  closeSidebarDrawer: () => set({ sidebarDrawerOpen: false }),
  openArtifactDrawer: () => set({ artifactDrawerOpen: true }),
  openSidebarDrawer: () => set({ sidebarDrawerOpen: true }),
  setLanguage: (value) => set({ language: value }),
  setSessionSearchQuery: (value) => set({ sessionSearchQuery: value }),
  setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
}));
