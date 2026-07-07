"use client";

import { SkillCard } from "../skills/skill-card";
import { useChatStore } from "@/stores";

export function SkillShortcuts() {
  const skills = useChatStore((state) => state.skills);
  const createSession = useChatStore((state) => state.createSession);

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
            onClick={() => createSession(skill.key)}
          />
        ))}
      </div>
    </section>
  );
}
