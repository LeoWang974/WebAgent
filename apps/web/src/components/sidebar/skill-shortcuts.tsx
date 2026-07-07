"use client";

import { SkillCard } from "../skills/skill-card";
import { useChatStore, useUiStore } from "@/stores";

export function SkillShortcuts() {
  const skills = useChatStore((state) => state.skills);
  const createSession = useChatStore((state) => state.createSession);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);

  return (
    <section className="space-y-2">
      <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Skills
      </h2>
      <div className="space-y-1">
        {skills.map((skill) => (
          <SkillCard
            description={skill.version}
            key={skill.key}
            name={skill.name}
            onClick={() => {
              closeArtifactDrawer();
              createSession(skill.key);
            }}
          />
        ))}
      </div>
    </section>
  );
}
