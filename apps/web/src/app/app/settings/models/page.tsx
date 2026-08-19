/**
 * File purpose: Defines the Next.js page route or route layout.
 * Main declarations: ModelSettingsPage handles model settings page.
 */

"use client";

import { ModelSettings } from "@/components/settings";
import { useI18n } from "@/lib/i18n";
import Link from "next/link";

export default function ModelSettingsPage() {
  const { t } = useI18n();

  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <Link
            className="text-sm text-muted-foreground hover:text-foreground"
            href="/app/settings"
          >
            {t("backToSettings")}
          </Link>
          <h1 className="text-2xl font-semibold">{t("modelConfiguration")}</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            {t("modelDescription")}
          </p>
        </header>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <ModelSettings />
        </section>
      </div>
    </main>
  );
}
