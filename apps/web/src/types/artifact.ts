export type ArtifactType =
  | "markdown_report"
  | "ppt_deck"
  | "image_result"
  | "data_table"
  | "chart";

export type ArtifactStatus = "pending" | "rendering" | "ready" | "failed";

export interface Artifact {
  id: string;
  sessionId: string;
  type: ArtifactType;
  title: string;
  status: ArtifactStatus;
}

