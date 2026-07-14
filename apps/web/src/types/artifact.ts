export type ArtifactType =
  | "markdown_report"
  | "html_page"
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

export interface SlidePreview {
  content?: string;
  contentType: string;
  id: string;
  index: number;
  title: string;
}

export interface ArtifactSlides {
  artifactId: string;
  slides: SlidePreview[];
  source: string;
}

export interface FileAsset {
  contentType: string;
  createdAt: string;
  filename: string;
  id: string;
  metadata?: Record<string, unknown>;
  sessionId?: string;
  size: number;
  url?: string;
}
