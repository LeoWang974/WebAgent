"use client";

import { useState } from "react";
import { CheckCircle2, Loader2, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useChatStore } from "@/stores";
import type { ModelProvider } from "@/types";

const providerOptions: Array<{ label: string; value: ModelProvider }> = [
  { label: "sensenova", value: "sensenova" },
  { label: "OpenAI compatible", value: "openai_compatible" },
  { label: "Custom", value: "custom" },
];

export function ModelSettings() {
  const { t } = useI18n();
  const addModel = useChatStore((state) => state.addModel);
  const deleteModel = useChatStore((state) => state.deleteModel);
  const models = useChatStore((state) => state.models);
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const selectModel = useChatStore((state) => state.selectModel);
  const setDefaultModel = useChatStore((state) => state.setDefaultModel);
  const testModelConnection = useChatStore((state) => state.testModelConnection);
  const testingModelId = useChatStore((state) => state.testingModelId);
  const updateModel = useChatStore((state) => state.updateModel);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [editingModelId, setEditingModelId] = useState<string>();
  const [editBaseUrl, setEditBaseUrl] = useState("");
  const [editName, setEditName] = useState("");
  const [editProvider, setEditProvider] = useState<ModelProvider>("openai_compatible");
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<ModelProvider>("openai_compatible");

  function handleAddModel() {
    const trimmedName = name.trim();

    if (!trimmedName) {
      return;
    }

    void addModel({
      baseUrl: baseUrl.trim() || undefined,
      maskedApiKey: apiKey.trim() ? "sk-****" : undefined,
      name: trimmedName,
      provider,
    });
    setApiKey("");
    setBaseUrl("");
    setName("");
    setProvider("openai_compatible");
  }

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">{t("modelConfiguration")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("modelSettingsDescription")}
        </p>
      </div>

      <div className="space-y-2">
        {models.map((model) => (
          <div
            className={`rounded-lg border bg-[#fbfbfa] p-3 ${
              selectedModelId === model.id ? "ring-1 ring-[#242424]" : ""
            }`}
            key={model.id}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                {editingModelId === model.id ? (
                  <div className="grid gap-2 md:grid-cols-3">
                    <input
                      className="rounded-md border px-2 py-1.5 text-sm"
                      onChange={(event) => setEditName(event.target.value)}
                      value={editName}
                    />
                    <select
                      className="rounded-md border bg-white px-2 py-1.5 text-sm"
                      onChange={(event) =>
                        setEditProvider(event.target.value as ModelProvider)
                      }
                      value={editProvider}
                    >
                      {providerOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <input
                      className="rounded-md border px-2 py-1.5 text-sm"
                      onChange={(event) => setEditBaseUrl(event.target.value)}
                      placeholder="https://api.example.com/v1"
                      value={editBaseUrl}
                    />
                  </div>
                ) : (
                  <button
                    className="min-w-0 text-left"
                    onClick={() => selectModel(model.id)}
                    type="button"
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">
                        {model.name}
                      </span>
                      {model.isDefault ? (
                        <span className="rounded-full border bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
                          {t("defaultModel")}
                        </span>
                      ) : null}
                      {model.isAvailable ? (
                        <CheckCircle2 className="size-3.5 text-emerald-600" />
                      ) : null}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {model.provider}
                      {model.baseUrl ? ` / ${model.baseUrl}` : ""}
                    </div>
                    {model.maskedApiKey ? (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {model.maskedApiKey}
                      </div>
                    ) : null}
                  </button>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {editingModelId === model.id ? (
                  <>
                    <button
                      className="flex size-7 items-center justify-center rounded-md border bg-white hover:bg-muted"
                      onClick={() => {
                        void updateModel(model.id, {
                          baseUrl: editBaseUrl.trim() || undefined,
                          name: editName.trim() || model.name,
                          provider: editProvider,
                        });
                        setEditingModelId(undefined);
                      }}
                      title={t("save")}
                      type="button"
                    >
                      <Save className="size-3.5" />
                    </button>
                    <button
                      className="flex size-7 items-center justify-center rounded-md border bg-white hover:bg-muted"
                      onClick={() => setEditingModelId(undefined)}
                      title={t("cancel")}
                      type="button"
                    >
                      <X className="size-3.5" />
                    </button>
                  </>
                ) : (
                  <button
                    className="flex size-7 items-center justify-center rounded-md border bg-white text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => {
                      setEditingModelId(model.id);
                      setEditBaseUrl(model.baseUrl ?? "");
                      setEditName(model.name);
                      setEditProvider(model.provider);
                    }}
                    title={t("edit")}
                    type="button"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                )}
                <button
                  className="rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted disabled:opacity-40"
                  disabled={model.isDefault}
                  onClick={() => void setDefaultModel(model.id)}
                  type="button"
                >
                  {t("setDefault")}
                </button>
                <button
                  className="flex h-7 items-center gap-1 rounded-md border bg-white px-2 text-xs hover:bg-muted disabled:opacity-40"
                  disabled={testingModelId === model.id}
                  onClick={() => void testModelConnection(model.id)}
                  type="button"
                >
                  {testingModelId === model.id ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : null}
                  {t("testConnection")}
                </button>
                <button
                  className="flex size-7 items-center justify-center rounded-md border bg-white text-muted-foreground hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                  disabled={model.isDefault}
                  onClick={() => void deleteModel(model.id)}
                  title={t("deleteModel")}
                  type="button"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <form
        className="space-y-3 rounded-lg border bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          handleAddModel();
        }}
      >
        <div>
          <h3 className="text-sm font-semibold">{t("addModel")}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {t("addModelDescription")}
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("modelName")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              autoComplete="off"
              onChange={(event) => setName(event.target.value)}
              placeholder="my-model"
              value={name}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("provider")}</span>
            <select
              className="w-full rounded-md border bg-white px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setProvider(event.target.value as ModelProvider)}
              value={provider}
            >
              {providerOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("baseUrl")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              autoComplete="url"
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://api.example.com/v1"
              value={baseUrl}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("apiKey")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              autoComplete="new-password"
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-..."
              type="password"
              value={apiKey}
            />
          </label>
        </div>
        <button
          className="flex h-9 items-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white hover:bg-[#111] disabled:opacity-40"
          disabled={!name.trim()}
          type="submit"
        >
          <Plus className="size-4" />
          {t("addModel")}
        </button>
      </form>
    </section>
  );
}
