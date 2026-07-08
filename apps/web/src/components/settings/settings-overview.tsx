"use client";

import { useI18n, type TranslationKey } from "@/lib/i18n";
import { Database, KeyRound, Settings2, Sparkles, UserRound } from "lucide-react";
import { DataContextSettingsPanel } from "./data-context-settings";
import { LanguageSettings } from "./language-settings";
import { ModelSettings } from "./model-settings";
import { ProfileSettings } from "./profile-settings";
import { SkillSettings } from "./skill-settings";

const sections: Array<{
  descriptionKey: TranslationKey;
  href: string;
  icon: typeof UserRound;
  key: TranslationKey;
}> = [
  {
    descriptionKey: "profileDescription",
    href: "#profile",
    icon: UserRound,
    key: "profile",
  },
  {
    descriptionKey: "languageAndInterfaceDescription",
    href: "#interface",
    icon: Settings2,
    key: "languageAndInterface",
  },
  {
    descriptionKey: "modelDescription",
    href: "#models",
    icon: KeyRound,
    key: "modelConfiguration",
  },
  {
    descriptionKey: "skillSettingsDescription",
    href: "#skills",
    icon: Sparkles,
    key: "skillManagement",
  },
  {
    descriptionKey: "dataSettingsDescription",
    href: "#data",
    icon: Database,
    key: "dataAndContext",
  },
];

export function SettingsOverview() {
  const { t } = useI18n();

  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:grid-cols-[240px_1fr]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <div className="mb-5 space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("workspaceSettings")}
            </p>
            <h1 className="text-2xl font-semibold">{t("settings")}</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              {t("settingsDescription")}
            </p>
          </div>
          <nav className="grid gap-1 rounded-lg border bg-white p-1 shadow-sm">
            {sections.map((section) => {
              const Icon = section.icon;

              return (
                <a
                  className="flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                  href={section.href}
                  key={section.href}
                >
                  <Icon className="size-4" />
                  <span>{t(section.key)}</span>
                </a>
              );
            })}
          </nav>
        </aside>

        <div className="space-y-4">
          <section className="rounded-lg border bg-white p-5 shadow-sm" id="profile">
            <ProfileSettings />
          </section>

          <section className="rounded-lg border bg-white p-5 shadow-sm" id="interface">
            <LanguageSettings />
          </section>

          <section className="rounded-lg border bg-white p-5 shadow-sm" id="models">
            <ModelSettings />
          </section>

          <section className="rounded-lg border bg-white p-5 shadow-sm" id="skills">
            <SkillSettings />
          </section>

          <section className="rounded-lg border bg-white p-5 shadow-sm" id="data">
            <DataContextSettingsPanel />
          </section>
        </div>
      </div>
    </main>
  );
}
