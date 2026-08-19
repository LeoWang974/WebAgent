/**
 * File purpose: Renders and coordinates the data context settings user-interface feature.
 * Main declarations: Toggle handles toggle; DataContextSettingsPanel handles data context settings
 * panel.
 */

"use client";

import { FormEvent, useEffect, useState } from "react";
import { Loader2, Save, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useSettingsStore } from "@/stores";
import type { DataContextSettings } from "@/types";

const fallbackSettings: DataContextSettings = {
  autoSummarizeContext: true,
  contextRetentionDays: 30,
  maxContextMessages: 40,
  saveConversationHistory: true,
  saveUploadedFiles: true,
};

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      aria-pressed={checked}
      className={`h-6 w-11 rounded-full p-0.5 transition ${
        checked ? "bg-[#242424]" : "bg-[#d9d9d2]"
      }`}
      onClick={() => onChange(!checked)}
      type="button"
    >
      <span
        className={`block size-5 rounded-full bg-white transition ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export function DataContextSettingsPanel() {
  const { t } = useI18n();
  const settings = useSettingsStore((state) => state.dataContextSettings);
  const hydrate = useSettingsStore((state) => state.hydrate);
  const saving = useSettingsStore((state) => state.saving);
  const savedAt = useSettingsStore((state) => state.savedAt);
  const updateDataContextSettings = useSettingsStore(
    (state) => state.updateDataContextSettings,
  );
  const [draft, setDraft] = useState<DataContextSettings>(
    settings ?? fallbackSettings,
  );

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (settings) {
      setDraft(settings);
    }
  }, [settings]);

  const source = settings ?? fallbackSettings;
  const dirty = JSON.stringify(draft) !== JSON.stringify(source);

  function updateDraft(input: Partial<DataContextSettings>) {
    setDraft((current) => ({ ...current, ...input }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await updateDataContextSettings(draft);
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div>
        <h2 className="text-base font-semibold">{t("dataAndContext")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("dataSettingsDescription")}
        </p>
      </div>

      <div className="space-y-3">
        {[
          {
            checked: draft.saveConversationHistory,
            description: t("saveConversationHistoryDescription"),
            label: t("saveConversationHistory"),
            onChange: (value: boolean) =>
              updateDraft({ saveConversationHistory: value }),
          },
          {
            checked: draft.saveUploadedFiles,
            description: t("saveUploadedFilesDescription"),
            label: t("saveUploadedFiles"),
            onChange: (value: boolean) => updateDraft({ saveUploadedFiles: value }),
          },
          {
            checked: draft.autoSummarizeContext,
            description: t("autoSummarizeContextDescription"),
            label: t("autoSummarizeContext"),
            onChange: (value: boolean) =>
              updateDraft({ autoSummarizeContext: value }),
          },
        ].map((item) => (
          <div
            className="flex items-center justify-between gap-4 rounded-lg border bg-[#fbfbfa] p-3"
            key={item.label}
          >
            <div>
              <div className="text-sm font-medium">{item.label}</div>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.description}
              </p>
            </div>
            <Toggle checked={item.checked} onChange={item.onChange} />
          </div>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1 rounded-lg border bg-[#fbfbfa] p-3">
          <span className="text-sm font-medium">{t("contextRetentionDays")}</span>
          <input
            className="mt-2 w-full accent-[#242424]"
            max={365}
            min={1}
            onChange={(event) =>
              updateDraft({ contextRetentionDays: Number(event.target.value) })
            }
            type="range"
            value={draft.contextRetentionDays}
          />
          <span className="text-xs text-muted-foreground">
            {draft.contextRetentionDays} {t("days")}
          </span>
        </label>
        <label className="space-y-1 rounded-lg border bg-[#fbfbfa] p-3">
          <span className="text-sm font-medium">{t("maxContextMessages")}</span>
          <input
            className="mt-2 w-full accent-[#242424]"
            max={200}
            min={10}
            onChange={(event) =>
              updateDraft({ maxContextMessages: Number(event.target.value) })
            }
            step={5}
            type="range"
            value={draft.maxContextMessages}
          />
          <span className="text-xs text-muted-foreground">
            {draft.maxContextMessages} {t("messages")}
          </span>
        </label>
      </div>

      <div className="rounded-lg border border-red-100 bg-red-50 p-3">
        <div className="text-sm font-semibold text-red-700">{t("dangerZone")}</div>
        <p className="mt-1 text-xs leading-5 text-red-700/80">
          {t("dangerZoneDescription")}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="flex h-8 items-center gap-1.5 rounded-md border border-red-200 bg-white px-2 text-xs text-red-700 hover:bg-red-50"
            type="button"
          >
            <Trash2 className="size-3.5" />
            {t("clearHistory")}
          </button>
          <button
            className="flex h-8 items-center gap-1.5 rounded-md border border-red-200 bg-white px-2 text-xs text-red-700 hover:bg-red-50"
            type="button"
          >
            <Trash2 className="size-3.5" />
            {t("clearUploadedFiles")}
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t pt-4">
        <div className="text-xs text-muted-foreground">
          {savedAt ? t("saved") : dirty ? t("unsavedChanges") : t("upToDate")}
        </div>
        <button
          className="flex h-9 items-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white hover:bg-[#111] disabled:opacity-40"
          disabled={!dirty || saving}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          {t("save")}
        </button>
      </div>
    </form>
  );
}
