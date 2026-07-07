export type SkillKey =
  | "data_analysis"
  | "deep_research"
  | "ppt_generation"
  | "u1_image";

export interface Skill {
  key: SkillKey;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
}

