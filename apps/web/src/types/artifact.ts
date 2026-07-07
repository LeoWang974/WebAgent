export type ArtifactType =
  | "markdown_report"
  | "ppt_deck"
  | "image_result"
  | "data_table"
  | "chart";

export type ArtifactStatus = "pending" | "rendering" | "ready" | "failed";

export interface Artifact {
  content?: string;
  id: string;
  metadata?: Record<string, unknown>;
  sessionId: string;
  type: ArtifactType;
  title: string;
  status: ArtifactStatus;
}
