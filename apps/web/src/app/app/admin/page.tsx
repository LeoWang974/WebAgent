"use client";

import { type TranslationKey, useI18n } from "@/lib/i18n";

const skills: Array<{ nameKey: TranslationKey; version: string }> = [
  { nameKey: "dataAnalysis", version: "1.0.0" },
  { nameKey: "deepResearch", version: "1.0.0" },
  { nameKey: "createPpt", version: "1.0.0" },
  { nameKey: "imageGeneration", version: "1.0.0" },
];

export default function AdminPage() {
  const { t } = useI18n();

  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("admin")}
          </p>
          <h1 className="text-2xl font-semibold">{t("skillManagement")}</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            {t("adminDescription")}
          </p>
        </header>

        <section className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <div className="grid grid-cols-[1fr_120px_140px_180px] border-b bg-[#f7f7f5] px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <span>{t("skill")}</span>
            <span>{t("version")}</span>
            <span>{t("status")}</span>
            <span>{t("actions")}</span>
          </div>
          {skills.map((skill) => (
            <div
              className="grid grid-cols-[1fr_120px_140px_180px] items-center border-b px-4 py-3 text-sm last:border-b-0"
              key={skill.nameKey}
            >
              <span className="font-medium">{t(skill.nameKey)}</span>
              <span className="text-muted-foreground">{skill.version}</span>
              <span>
                <span className="rounded-full border bg-white px-2 py-1 text-xs text-muted-foreground">
                  {t("published")}
                </span>
              </span>
              <span className="flex gap-2">
                <button
                  className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                  type="button"
                >
                  {t("newVersion")}
                </button>
                <button
                  className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                  type="button"
                >
                  {t("rollback")}
                </button>
              </span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
