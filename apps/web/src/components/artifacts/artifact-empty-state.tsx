"use client";

import { useI18n } from "@/lib/i18n";

export function ArtifactEmptyState() {
  const { t } = useI18n();

  return (
    <div className="flex min-h-80 flex-col items-center justify-center rounded-lg border border-dashed bg-white p-6 text-center text-sm text-muted-foreground">
      <div className="mb-3 flex size-10 items-center justify-center rounded-lg border bg-[#f7f7f5]">
        +
      </div>
      <div className="font-medium text-foreground">{t("artifactEmptyTitle")}</div>
      <p className="mt-1 max-w-sm leading-6">{t("artifactEmptyDescription")}</p>
    </div>
  );
}
