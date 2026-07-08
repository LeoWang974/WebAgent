"use client";

import { useI18n } from "@/lib/i18n";

export function ProfileSettings() {
  const { t } = useI18n();

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold">{t("profile")}</h2>
      <input
        className="w-full rounded-md border px-3 py-2 text-sm"
        placeholder={t("profile")}
      />
    </section>
  );
}
