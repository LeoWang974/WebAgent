/**
 * File purpose: Renders and coordinates the language settings user-interface feature.
 * Main declarations: LanguageSettings handles language settings.
 */

"use client";

import { useEffect } from "react";
import { useI18n } from "@/lib/i18n";
import {
  useChatStore,
  useSettingsStore,
  useUiStore,
  type AppLanguage,
  type AppTheme,
  type SendShortcut,
} from "@/stores";

const languageOptions: Array<{ label: string; value: AppLanguage }> = [
  { label: "\u4e2d\u6587", value: "zh-CN" },
  { label: "English", value: "en-US" },
];

const shortcutOptions: Array<{
  labelKey: "enterToSend" | "modEnterToSend";
  value: SendShortcut;
}> = [
  { labelKey: "enterToSend", value: "enter" },
  { labelKey: "modEnterToSend", value: "mod-enter" },
];

const themeOptions: Array<{
  labelKey: "themeLight" | "themeDark" | "themeSystem";
  value: AppTheme;
}> = [
  { labelKey: "themeLight", value: "light" },
  { labelKey: "themeDark", value: "dark" },
  { labelKey: "themeSystem", value: "system" },
];

export function LanguageSettings() {
  const { language, t } = useI18n();
  const artifactPanelOpen = useUiStore((state) => state.artifactPanelOpen);
  const artifactPanelWidth = useUiStore((state) => state.artifactPanelWidth);
  const sendShortcut = useUiStore((state) => state.sendShortcut);
  const theme = useUiStore((state) => state.theme);
  const setArtifactPanelOpen = useUiStore((state) => state.setArtifactPanelOpen);
  const setArtifactPanelWidth = useUiStore((state) => state.setArtifactPanelWidth);
  const setLanguage = useUiStore((state) => state.setLanguage);
  const setSendShortcut = useUiStore((state) => state.setSendShortcut);
  const setTheme = useUiStore((state) => state.setTheme);
  const interfaceSettings = useSettingsStore((state) => state.interfaceSettings);
  const settingsError = useSettingsStore((state) => state.error);
  const settingsSaving = useSettingsStore((state) => state.saving);
  const hydrateSettings = useSettingsStore((state) => state.hydrate);
  const updateInterfaceSettings = useSettingsStore((state) => state.updateInterfaceSettings);
  const refreshArtifacts = useChatStore((state) => state.refreshArtifacts);
  const developerMode = interfaceSettings?.developerMode ?? false;

  useEffect(() => {
    void hydrateSettings();
  }, [hydrateSettings]);

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">{t("languageAndInterface")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("languageAndInterfaceDescription")}
        </p>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium">{t("language")}</div>
        <div className="inline-flex rounded-lg border bg-[#f7f7f5] p-1">
          {languageOptions.map((option) => (
            <button
              className={`rounded-md px-3 py-1.5 text-sm ${
                language === option.value
                  ? "bg-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              key={option.value}
              onClick={() => setLanguage(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium">{t("theme")}</div>
        <div className="inline-flex rounded-lg border bg-[#f7f7f5] p-1">
          {themeOptions.map((option) => (
            <button
              className={`rounded-md px-3 py-1.5 text-sm ${
                theme === option.value
                  ? "bg-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              key={option.value}
              onClick={() => setTheme(option.value)}
              type="button"
            >
              {t(option.labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium">{t("sendShortcut")}</div>
        <div className="inline-flex rounded-lg border bg-[#f7f7f5] p-1">
          {shortcutOptions.map((option) => (
            <button
              className={`rounded-md px-3 py-1.5 text-sm ${
                sendShortcut === option.value
                  ? "bg-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              key={option.value}
              onClick={() => setSendShortcut(option.value)}
              type="button"
            >
              {t(option.labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border bg-[#fbfbfa] p-3">
        <div>
          <div className="text-sm font-medium">{t("showArtifactPanel")}</div>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("showArtifactPanelDescription")}
          </p>
        </div>
        <button
          aria-pressed={artifactPanelOpen}
          className={`h-6 w-11 rounded-full p-0.5 transition ${
            artifactPanelOpen ? "bg-[#242424]" : "bg-[#d9d9d2]"
          }`}
          onClick={() => setArtifactPanelOpen(!artifactPanelOpen)}
          type="button"
        >
          <span
            className={`block size-5 rounded-full bg-white transition ${
              artifactPanelOpen ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      <div className="space-y-2 rounded-lg border bg-[#fbfbfa] p-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium">{t("artifactPanelWidth")}</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("artifactPanelWidthDescription")}
            </p>
          </div>
          <div className="text-sm font-semibold">{artifactPanelWidth}px</div>
        </div>
        <input
          className="w-full accent-[#242424]"
          max={720}
          min={320}
          onChange={(event) => setArtifactPanelWidth(Number(event.target.value))}
          step={20}
          type="range"
          value={artifactPanelWidth}
        />
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border bg-[#fbfbfa] p-3">
        <div>
          <div className="text-sm font-medium">{t("developerMode")}</div>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("developerModeDescription")}
          </p>
        </div>
        <button
          aria-pressed={developerMode}
          className={`h-6 w-11 rounded-full p-0.5 transition ${
            developerMode ? "bg-[#242424]" : "bg-[#d9d9d2]"
          }`}
          disabled={settingsSaving}
          onClick={() => {
            const nextSettings = { developerMode: !developerMode };
            void updateInterfaceSettings(nextSettings).then(() => {
              void refreshArtifacts();
            });
          }}
          type="button"
        >
          <span
            className={`block size-5 rounded-full bg-white transition ${
              developerMode ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>
      {settingsError ? (
        <p className="-mt-3 text-xs text-red-600">{settingsError}</p>
      ) : null}
    </section>
  );
}
