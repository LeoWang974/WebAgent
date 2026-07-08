"use client";

import { useChatStore } from "@/stores";
import type { SkillKey } from "@/types";
import { BarChart3, Image, Presentation, Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function EmptyConversation() {
  const { t } = useI18n();
  const createSession = useChatStore((state) => state.createSession);
  const prompts = [
    {
      description: t("analyzeDataDescription"),
      icon: BarChart3,
      skillKey: "data_analysis" as SkillKey,
      title: t("analyzeDataTitle"),
    },
    {
      description: t("deepResearchDescription"),
      icon: Search,
      skillKey: "deep_research" as SkillKey,
      title: t("deepResearch"),
    },
    {
      description: t("createPptDescription"),
      icon: Presentation,
      skillKey: "ppt_generation" as SkillKey,
      title: t("createPpt"),
    },
    {
      description: t("generateImageDescription"),
      icon: Image,
      skillKey: "u1_image" as SkillKey,
      title: t("generateImageTitle"),
    },
  ];

  return (
    <div className="mx-auto flex min-h-[420px] max-w-3xl flex-col justify-center py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">{t("emptyTitle")}</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          {t("emptyDescription")}
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {prompts.map((prompt) => {
          const Icon = prompt.icon;

          return (
            <button
              className="rounded-xl border bg-white p-4 text-left shadow-sm hover:bg-[#fafafa]"
              key={prompt.skillKey}
              onClick={() => createSession(prompt.skillKey)}
              type="button"
            >
              <div className="mb-3 flex size-9 items-center justify-center rounded-lg border bg-[#f7f7f5]">
                <Icon className="size-4" />
              </div>
              <div className="text-sm font-semibold">{prompt.title}</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {prompt.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
