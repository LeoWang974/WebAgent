import type { Artifact } from "@/types";
import { ArtifactEmptyState } from "./artifact-empty-state";
import { DataPreviewPlaceholder } from "./data-preview-placeholder";
import { DataTableViewer } from "./data-table-viewer";
import { FileArtifactViewer } from "./file-artifact-viewer";
import { HtmlViewer } from "./html-viewer";
import { ImageViewer } from "./image-viewer";
import { MarkdownPreviewPlaceholder } from "./markdown-preview-placeholder";
import { MarkdownViewer } from "./markdown-viewer";
import { PptViewer } from "./ppt-viewer";

interface ArtifactPreviewContentProps {
  artifact?: Artifact;
}

function getMetadata<T>(artifact: Artifact): Partial<T> {
  return (artifact.metadata ?? {}) as Partial<T>;
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

  if (artifact.type === "html_page") {
    if (artifact.content) {
      return <HtmlViewer content={artifact.content} title={artifact.title} />;
    }

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="HTML 文件已生成，可以下载原文件；当前 artifact 暂无可嵌入的网页内容。"
      />
    );
  }

  if (artifact.type === "ppt_deck") {
    const metadata = getMetadata<{
      slides: Array<{
        bullets?: string[];
        eyebrow?: string;
        subtitle?: string;
        title: string;
      }>;
    }>(artifact);

    if (metadata.slides?.length) {
      return <PptViewer slides={metadata.slides} title={artifact.title} />;
    }

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="PPT 文件已生成。浏览器内幻灯片渲染服务接入前，可以直接下载原始 .pptx。"
      />
    );
  }

  if (artifact.type === "image_result") {
    const metadata = getMetadata<{
      images: Array<{
        gradient?: string;
        id: string;
        prompt: string;
        url?: string;
      }>;
    }>(artifact);

    if (metadata.images?.length) {
      return <ImageViewer images={metadata.images} title={artifact.title} />;
    }

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="图片文件已生成。当前没有可嵌入的图片 URL，可以下载原图查看。"
      />
    );
  }

  if (artifact.type === "data_table" || artifact.type === "chart") {
    const metadata = getMetadata<{
      columns: string[];
      rows: string[][];
      summary?: Array<{ label: string; value: string }>;
    }>(artifact);

    if (metadata.columns?.length && metadata.rows?.length) {
      return (
        <DataTableViewer
          columns={metadata.columns}
          rows={metadata.rows}
          summary={metadata.summary}
          title={artifact.title}
        />
      );
    }

    return <DataPreviewPlaceholder />;
  }

  return <ArtifactEmptyState />;
}
