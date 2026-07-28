"use client";

import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";
import type { ModelConfig } from "@/types";

type AgentKey = "hermes" | "openclaw";

const AGENTS: Array<{ key: AgentKey; label: string }> = [
  { key: "hermes", label: "Hermes" },
  { key: "openclaw", label: "OpenClaw" },
];

function isRuntimeAdapterModel(model: ModelConfig) {
  const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
  return (
    marker.includes("openclaw") ||
    marker.includes("hermes") ||
    marker.includes("18789") ||
    marker.includes("8642")
  );
}

function runtimeLabel(agentKey: AgentKey, models: ModelConfig[]) {
  const runtimeModel = models.find((model) => {
    const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
    return agentKey === "openclaw"
      ? marker.includes("openclaw") || marker.includes("18789")
      : marker.includes("hermes") || marker.includes("8642");
  });

  if (!runtimeModel) {
    return `${agentKey} 状态未知`;
  }
  if (runtimeModel.isAvailable === false) {
    return runtimeModel.runtimeStatus?.message ?? `${runtimeModel.name} 不可用`;
  }
  return runtimeModel.runtimeStatus?.message ?? `${runtimeModel.name} 可用`;
}

function optionLabel(model: ModelConfig, defaultLabel: string) {
  const parts = [model.name];
  if (model.isDefault) {
    parts.push(`(${defaultLabel})`);
  }
  if (model.isAvailable === false) {
    parts.push("不可用");
  }
  return parts.join(" ");
}

export function ModelSelector() {
  const { t } = useI18n();
  const loading = useChatStore((state) => state.loading);
  const models = useChatStore((state) => state.models);
  const selectedAgentKey = useChatStore((state) => state.selectedAgentKey);
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const selectAgent = useChatStore((state) => state.selectAgent);
  const selectModel = useChatStore((state) => state.selectModel);
  const apiModels = models.filter((model) => !isRuntimeAdapterModel(model));
  const selectedModel = apiModels.find((model) => model.id === selectedModelId);
  const agentAvailable =
    !models.some((model) => {
      const marker = `${model.name} ${model.baseUrl ?? ""}`.toLowerCase();
      const matches =
        selectedAgentKey === "openclaw"
          ? marker.includes("openclaw") || marker.includes("18789")
          : marker.includes("hermes") || marker.includes("8642");
      return matches && model.isAvailable === false;
    });

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`size-2 rounded-full ${
          agentAvailable ? "bg-emerald-500" : "bg-amber-500"
        }`}
        title={runtimeLabel(selectedAgentKey, models)}
      />
      <select
        className="h-8 max-w-[110px] rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground disabled:opacity-50"
        disabled={loading}
        onChange={(event) => selectAgent(event.target.value as AgentKey)}
        title="选择 Agent 运行时"
        value={selectedAgentKey}
      >
        {AGENTS.map((agent) => (
          <option key={agent.key} value={agent.key}>
            {agent.label}
          </option>
        ))}
      </select>
      <select
        className="h-8 max-w-[190px] rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground disabled:opacity-50"
        disabled={loading || apiModels.length === 0}
        onChange={(event) => selectModel(event.target.value)}
        title={selectedModel?.baseUrl ?? selectedModel?.name ?? t("loadingModels")}
        value={selectedModelId ?? ""}
      >
        {apiModels.length === 0 ? (
          <option value="">{t("loadingModels")}</option>
        ) : null}
        {apiModels.map((model) => (
          <option key={model.id} value={model.id}>
            {optionLabel(model, t("defaultModel"))}
          </option>
        ))}
      </select>
    </div>
  );
}
