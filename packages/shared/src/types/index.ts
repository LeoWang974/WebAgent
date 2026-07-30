export type SkillKey =
  | "data_analysis"
  | "deep_research"
  | "html_generation"
  | "ppt_generation"
  | "u1_image";

export type SessionStatus = "active" | "running" | "failed" | "completed";

export type MessageRole = "user" | "assistant" | "system" | "tool";

export type ArtifactType =
  | "debug_json"
  | "html_page"
  | "markdown_report"
  | "ppt_deck"
  | "image_result"
  | "data_table"
  | "chart";
