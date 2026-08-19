/**
 * File purpose: Defines shared TypeScript contracts for settings.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

export interface DataContextSettings {
  autoSummarizeContext: boolean;
  contextRetentionDays: number;
  maxContextMessages: number;
  saveConversationHistory: boolean;
  saveUploadedFiles: boolean;
}

export interface InterfaceSettings {
  developerMode: boolean;
}
