import type { ModelConfig } from "@/types";

export type AgentKey = "hermes" | "openclaw";

export function isRuntimeAdapterModel(model: ModelConfig) {
  const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
  return (
    marker.includes("openclaw") ||
    marker.includes("hermes") ||
    marker.includes("18789") ||
    marker.includes("8642")
  );
}

export function isAgentRuntimeModel(model: ModelConfig, agentKey: AgentKey) {
  const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
  return agentKey === "openclaw"
    ? marker.includes("openclaw") || marker.includes("18789")
    : marker.includes("hermes") || marker.includes("8642");
}
