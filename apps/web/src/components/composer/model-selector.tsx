"use client";

import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";
import type { ModelConfig } from "@/types";

function runtimeLabel(model?: ModelConfig) {
  if (!model) {
    return "未知";
  }
  const adapterKey = model.runtimeStatus?.adapterKey;
  if (adapterKey === "openclaw") {
    return model.isAvailable ? "OpenClaw Gateway 已连接" : "OpenClaw Gateway 未连接";
  }
  if (adapterKey === "hermes") {
    return model.isAvailable ? "Hermes 可用" : "Hermes 不可用";
  }
  return model.isAvailable === false ? "不可用" : "可用";
}

function optionLabel(model: ModelConfig, defaultLabel: string) {
  const parts = [model.name];
  if (model.isDefault) {
    parts.push(`(${defaultLabel})`);
  }
  if (model.runtimeStatus?.adapterKey || model.isAvailable === false) {
    parts.push(model.isAvailable ? "已连接" : "未连接");
  }
  return parts.join(" ");
}

export function ModelSelector() {
  const { t } = useI18n();
  const loading = useChatStore((state) => state.loading);
  const models = useChatStore((state) => state.models);
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const selectModel = useChatStore((state) => state.selectModel);
  const selectedModel = models.find((model) => model.id === selectedModelId);
  const isConnected = selectedModel?.isAvailable !== false;

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`size-2 rounded-full ${
          isConnected ? "bg-emerald-500" : "bg-amber-500"
        }`}
        title={selectedModel?.runtimeStatus?.message ?? runtimeLabel(selectedModel)}
      />
      <select
        className="h-8 max-w-[190px] rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground disabled:opacity-50"
        disabled={loading || models.length === 0}
        onChange={(event) => selectModel(event.target.value)}
        title={runtimeLabel(selectedModel)}
        value={selectedModelId ?? ""}
      >
        {models.length === 0 ? (
          <option value="">{t("loadingModels")}</option>
        ) : null}
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {optionLabel(model, t("defaultModel"))}
          </option>
        ))}
      </select>
    </div>
  );
}
