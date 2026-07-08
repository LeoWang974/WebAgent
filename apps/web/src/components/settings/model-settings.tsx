"use client";

import { useI18n } from "@/lib/i18n";
import { ModelConfigCard } from "./model-config-card";

export function ModelSettings() {
  const { t } = useI18n();

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold">{t("models")}</h2>
      <ModelConfigCard name="sensenova" provider="platform default" />
    </section>
  );
}
