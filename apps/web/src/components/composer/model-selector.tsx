"use client";

import { useI18n } from "@/lib/i18n";
import { useChatStore } from "@/stores";
import type { ModelConfig } from "@/types";

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
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const selectModel = useChatStore((state) => state.selectModel);
  const selectedModel = models.find((model) => model.id === selectedModelId);

  return (
    <div className="flex items-center gap-1.5">
      <span
        className="size-2 rounded-full bg-emerald-500"
        title="Hermes 运行时"
      />
      <span className="hidden text-xs text-muted-foreground sm:inline">Hermes</span>
      <select
        className="h-8 max-w-[190px] rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground disabled:opacity-50"
        disabled={loading || models.length === 0}
        onChange={(event) => selectModel(event.target.value)}
        title={selectedModel?.baseUrl ?? selectedModel?.name ?? t("loadingModels")}
        value={selectedModelId ?? ""}
      >
        {models.length === 0 ? <option value="">{t("loadingModels")}</option> : null}
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {optionLabel(model, t("defaultModel"))}
          </option>
        ))}
      </select>
    </div>
  );
}
