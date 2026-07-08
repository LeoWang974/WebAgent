export type ModelProvider = "sensenova" | "openai_compatible" | "custom";

export interface ModelConfig {
  baseUrl?: string;
  id: string;
  isAvailable?: boolean;
  name: string;
  provider: ModelProvider;
  isDefault: boolean;
  maskedApiKey?: string;
}
