"use client";

import { Loader2, RotateCcw, Star } from "lucide-react";
import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

export function SkillSettings() {
  const { t } = useI18n();
  const setDefaultSkill = useChatStore((state) => state.setDefaultSkill);
  const skills = useChatStore((state) => state.skills);
  const toggleSkillEnabled = useChatStore((state) => state.toggleSkillEnabled);
  const updateSkillVersion = useChatStore((state) => state.updateSkillVersion);
  const updatingSkillKey = useChatStore((state) => state.updatingSkillKey);

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">{t("skillManagement")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("skillSettingsDescription")}
        </p>
      </div>

      <div className="space-y-2">
        {skills.map((skill) => {
          const updating = updatingSkillKey === skill.key;

          return (
            <div className="rounded-lg border bg-[#fbfbfa] p-3" key={skill.key}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">
                      {skill.name}
                    </span>
                    {skill.isDefault ? (
                      <span className="rounded-full border bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
                        {t("defaultSkill")}
                      </span>
                    ) : null}
                    <span
                      className={`rounded-full border bg-white px-2 py-0.5 text-[11px] ${
                        skill.enabled ? "text-emerald-700" : "text-muted-foreground"
                      }`}
                    >
                      {skill.enabled ? t("enabled") : t("disabled")}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {skill.description}
                  </p>
                  <div className="mt-2 text-xs text-muted-foreground">
                    v{skill.version}
                    {skill.lastUpdatedAt
                      ? ` / ${new Date(skill.lastUpdatedAt).toLocaleDateString()}`
                      : ""}
                  </div>
                </div>

                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  <button
                    className="rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted disabled:opacity-40"
                    disabled={!skill.enabled || skill.isDefault}
                    onClick={() => void setDefaultSkill(skill.key)}
                    type="button"
                  >
                    <Star className="mr-1 inline size-3" />
                    {t("setDefault")}
                  </button>
                  <button
                    className="rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted"
                    onClick={() => void toggleSkillEnabled(skill.key)}
                    type="button"
                  >
                    {skill.enabled ? t("disable") : t("enable")}
                  </button>
                  <button
                    className="rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted disabled:opacity-40"
                    disabled={updating}
                    onClick={() => void updateSkillVersion(skill.key, "update")}
                    type="button"
                  >
                    {updating ? (
                      <Loader2 className="mr-1 inline size-3 animate-spin" />
                    ) : null}
                    {t("newVersion")}
                  </button>
                  <button
                    className="rounded-md border bg-white px-2 py-1 text-xs hover:bg-muted disabled:opacity-40"
                    disabled={updating}
                    onClick={() => void updateSkillVersion(skill.key, "rollback")}
                    type="button"
                  >
                    <RotateCcw className="mr-1 inline size-3" />
                    {t("rollback")}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
