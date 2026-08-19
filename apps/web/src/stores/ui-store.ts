/**
 * File purpose: Manages client state and actions for ui store.
 * Main declarations: useUiStore exposes the use ui store public API.
 */

"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AppLanguage = "zh-CN" | "en-US";
export type AppTheme = "light" | "dark" | "system";
export type SendShortcut = "enter" | "mod-enter";

interface UiState {
  artifactDrawerOpen: boolean;
  artifactFullscreenOpen: boolean;
  artifactPanelOpen: boolean;
  artifactPanelWidth: number;
  language: AppLanguage;
  sendShortcut: SendShortcut;
  sidebarDrawerOpen: boolean;
  sessionSearchQuery: string;
  sidebarCollapsed: boolean;
  theme: AppTheme;
  closeArtifactDrawer: () => void;
  closeArtifactFullscreen: () => void;
  closeSidebarDrawer: () => void;
  openArtifactDrawer: () => void;
  openArtifactFullscreen: () => void;
  openSidebarDrawer: () => void;
  setLanguage: (value: AppLanguage) => void;
  setArtifactPanelWidth: (value: number) => void;
  setSessionSearchQuery: (value: string) => void;
  setSendShortcut: (value: SendShortcut) => void;
  setSidebarCollapsed: (value: boolean) => void;
  setTheme: (value: AppTheme) => void;
  setArtifactPanelOpen: (value: boolean) => void;
  toggleArtifactPanel: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      artifactDrawerOpen: false,
      artifactFullscreenOpen: false,
      artifactPanelOpen: true,
      artifactPanelWidth: 420,
      language: "zh-CN",
      sendShortcut: "enter",
      sidebarDrawerOpen: false,
      sessionSearchQuery: "",
      sidebarCollapsed: false,
      theme: "light",
      closeArtifactDrawer: () => set({ artifactDrawerOpen: false }),
      closeArtifactFullscreen: () => set({ artifactFullscreenOpen: false }),
      closeSidebarDrawer: () => set({ sidebarDrawerOpen: false }),
      openArtifactDrawer: () => set({ artifactDrawerOpen: true }),
      openArtifactFullscreen: () => set({ artifactFullscreenOpen: true }),
      openSidebarDrawer: () => set({ sidebarDrawerOpen: true }),
      setArtifactPanelOpen: (value) => set({ artifactPanelOpen: value }),
      setArtifactPanelWidth: (value) =>
        set({ artifactPanelWidth: Math.min(720, Math.max(320, value)) }),
      setLanguage: (value) => set({ language: value }),
      setSendShortcut: (value) => set({ sendShortcut: value }),
      setSessionSearchQuery: (value) => set({ sessionSearchQuery: value }),
      setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
      setTheme: (value) => set({ theme: value }),
      toggleArtifactPanel: () =>
        set((state) => ({ artifactPanelOpen: !state.artifactPanelOpen })),
    }),
    {
      name: "webagent-ui-settings",
      partialize: (state) => ({
        artifactPanelOpen: state.artifactPanelOpen,
        artifactPanelWidth: state.artifactPanelWidth,
        language: state.language,
        sendShortcut: state.sendShortcut,
        theme: state.theme,
      }),
    },
  ),
);
