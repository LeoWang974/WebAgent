"use client";

import type { SkillKey } from "@/types";
import { useI18n } from "@/lib/i18n";

interface SkillSelectorProps {
  onChange?: (value: SkillKey | undefined) => void;
  value?: SkillKey;
}

export function SkillSelector({ onChange, value }: SkillSelectorProps) {
  const { t } = useI18n();

  return (
    <select
      className="h-8 rounded-md border bg-background px-2 text-xs text-muted-foreground outline-none hover:text-foreground"
      onChange={(event) =>
        onChange?.(
          event.target.value ? (event.target.value as SkillKey) : undefined,
        )
      }
      value={value ?? ""}
    >
      <option value="">{t("autoSkill")}</option>
      <option value="data_analysis">{t("dataAnalysis")}</option>
      <option value="deep_research">{t("deepResearch")}</option>
      <option value="ppt_generation">{t("createPpt")}</option>
      <option value="u1_image">{t("imageGeneration")}</option>
    </select>
  );
}
