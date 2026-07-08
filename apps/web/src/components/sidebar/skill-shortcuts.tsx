"use client";

import { SkillCard } from "../skills/skill-card";
import { useChatStore, useUiStore } from "@/stores";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";

export function SkillShortcuts() {
  const { t } = useI18n();
  const router = useRouter();
  const skills = useChatStore((state) => state.skills);
  const createSession = useChatStore((state) => state.createSession);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);

  return (
    <section className="space-y-2">
      <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t("skills")}
      </h2>
      <div className="space-y-1">
        {skills.map((skill) => (
          <SkillCard
            description={skill.version}
            key={skill.key}
            name={skill.name}
            onClick={async () => {
              closeArtifactDrawer();
              const session = await createSession(skill.key);
              router.push(session ? `/app/chat/${session.id}` : "/app");
            }}
          />
        ))}
      </div>
    </section>
  );
}
