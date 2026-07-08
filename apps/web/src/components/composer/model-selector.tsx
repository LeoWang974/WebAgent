"use client";

import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

export function ModelSelector() {
  const { t } = useI18n();
  const loading = useChatStore((state) => state.loading);
  const models = useChatStore((state) => state.models);
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const selectModel = useChatStore((state) => state.selectModel);

  return (
    <select
      className="h-8 max-w-[150px] rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground disabled:opacity-50"
      disabled={loading || models.length === 0}
      onChange={(event) => selectModel(event.target.value)}
      title={t("models")}
      value={selectedModelId ?? ""}
    >
      {models.length === 0 ? (
        <option value="">{t("loadingModels")}</option>
      ) : null}
      {models.map((model) => (
        <option key={model.id} value={model.id}>
          {model.name}
          {model.isDefault ? ` (${t("defaultModel")})` : ""}
        </option>
      ))}
    </select>
  );
}
