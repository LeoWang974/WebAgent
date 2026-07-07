import type { Artifact } from "@/types";
import { ArtifactEmptyState } from "./artifact-empty-state";
import { DataPreviewPlaceholder } from "./data-preview-placeholder";
import { ImagePreviewPlaceholder } from "./image-preview-placeholder";
import { MarkdownPreviewPlaceholder } from "./markdown-preview-placeholder";
import { MarkdownViewer } from "./markdown-viewer";
import { PptPreviewPlaceholder } from "./ppt-preview-placeholder";

interface ArtifactPreviewContentProps {
  artifact?: Artifact;
}

export function ArtifactPreviewContent({ artifact }: ArtifactPreviewContentProps) {
  if (!artifact) {
    return <ArtifactEmptyState />;
  }

  if (artifact.type === "markdown_report") {
    if (artifact.content) {
      return <MarkdownViewer content={artifact.content} title={artifact.title} />;
    }

    return <MarkdownPreviewPlaceholder />;
  }

  if (artifact.type === "ppt_deck") {
    return <PptPreviewPlaceholder />;
  }

  if (artifact.type === "image_result") {
    return <ImagePreviewPlaceholder />;
  }

  if (artifact.type === "data_table" || artifact.type === "chart") {
    return <DataPreviewPlaceholder />;
  }

  return <ArtifactEmptyState />;
}
