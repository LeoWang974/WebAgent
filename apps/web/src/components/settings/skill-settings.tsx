/**
 * File purpose: Renders and coordinates the skill settings user-interface feature.
 * Main declarations: SkillSettings handles skill settings.
 */

"use client";

import { Check, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

export function SkillSettings() {
  const { t } = useI18n();
  const skills = useChatStore((state) => state.skills);
  const updateSkills = useChatStore((state) => state.updateSkills);
  const updatingSkills = useChatStore((state) => state.updatingSkills);
  const [updateMessage, setUpdateMessage] = useState<string | undefined>();

  const enabledCount = skills.filter((skill) => skill.enabled).length;

  const handleUpdate = async () => {
    setUpdateMessage(undefined);
    try {
      await updateSkills();
      setUpdateMessage(t("skillsUpdated"));
    } catch {
      setUpdateMessage(t("skillsUpdateFailed"));
    }
  };

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">{t("skillManagement")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("skillSettingsDescription")}
        </p>
      </div>

      <div className="rounded-lg border bg-[#fbfbfa] p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold">SenseNova Skills</span>
              <span className="rounded-full border bg-white px-2 py-0.5 text-[11px] text-emerald-700">
                {enabledCount}/{skills.length} {t("enabled")}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {t("skillsBundleDescription")}
            </p>
            <div className="mt-2 text-xs text-muted-foreground">
              {t("installedSkills")}: {skills.length}
            </div>
            {updateMessage ? (
              <p className="mt-2 flex items-center gap-1 text-xs text-emerald-700">
                <Check className="size-3" />
                {updateMessage}
              </p>
            ) : null}
          </div>

          <button
            aria-label={t("updateSkills")}
            className="shrink-0 rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted disabled:opacity-40"
            disabled={updatingSkills}
            onClick={() => void handleUpdate()}
            type="button"
          >
            {updatingSkills ? (
              <Loader2 className="mr-1 inline size-3 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 inline size-3" />
            )}
            {updatingSkills ? t("updatingSkills") : t("updateSkills")}
          </button>
        </div>
      </div>
    </section>
  );
}
