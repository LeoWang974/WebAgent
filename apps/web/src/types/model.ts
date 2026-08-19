/**
 * File purpose: Defines shared TypeScript contracts for model.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

export type ModelProvider = "sensenova" | "openai_compatible" | "custom";

export interface ModelRuntimeStatus {
  adapterKey?: string;
  health?: Record<string, unknown>;
  message?: string;
  ok?: boolean;
  status?: "available" | "connected" | "unavailable" | string;
}

export interface ModelConfig {
  apiKey?: string;
  baseUrl?: string;
  id: string;
  isAvailable?: boolean;
  name: string;
  provider: ModelProvider;
  isDefault: boolean;
  maskedApiKey?: string;
  runtimeStatus?: ModelRuntimeStatus;
}
