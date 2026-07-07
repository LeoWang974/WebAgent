"use client";

import type { SkillKey } from "@/types";

interface SkillSelectorProps {
  onChange?: (value: SkillKey | undefined) => void;
  value?: SkillKey;
}

export function SkillSelector({ onChange, value }: SkillSelectorProps) {
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
      <option value="">Auto skill</option>
      <option value="data_analysis">数据分析</option>
      <option value="deep_research">深度调研</option>
      <option value="ppt_generation">PPT 生成</option>
      <option value="u1_image">u1 生图</option>
    </select>
  );
}
