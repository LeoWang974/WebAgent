"use client";

import { UserManagement } from "@/components/admin";
import { SkillSettings } from "@/components/settings";
import { useI18n } from "@/lib/i18n";

export default function AdminPage() {
  const { t } = useI18n();

  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("admin")}
          </p>
          <h1 className="text-2xl font-semibold">{t("admin")}</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            {t("adminDescription")}
          </p>
        </header>

        <section className="rounded-lg border bg-white p-5 shadow-sm">
          <UserManagement />
        </section>

        <section className="rounded-lg border bg-white p-5 shadow-sm">
          <SkillSettings />
        </section>
      </div>
    </main>
  );
}
