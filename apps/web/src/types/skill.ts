export type SkillKey =
  | "data_analysis"
  | "deep_research"
  | "html_generation"
  | "ppt_generation"
  | "u1_image";

export interface Skill {
  key: SkillKey;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  isDefault?: boolean;
  lastUpdatedAt?: string;
}
