/**
 * File purpose: Renders and coordinates the artifact preview content user-interface feature.
 * Main declarations: getMetadata handles get metadata; formatJsonContent handles format json
 * content; ArtifactPreviewContent handles artifact preview content.
 */

import type { Artifact } from "@/types";
import { ArtifactEmptyState } from "./artifact-empty-state";
import { DataTableViewer } from "./data-table-viewer";
import { FileArtifactViewer } from "./file-artifact-viewer";
import { HtmlViewer } from "./html-viewer";
import { ImageViewer } from "./image-viewer";
import { MarkdownViewer } from "./markdown-viewer";
import { PptArtifactViewer } from "./ppt-artifact-viewer";
import { PptViewer } from "./ppt-viewer";

interface ArtifactPreviewContentProps {
  artifact?: Artifact;
}

function getMetadata<T>(artifact: Artifact): Partial<T> {
  return (artifact.metadata ?? {}) as Partial<T>;
}

function formatJsonContent(content?: string) {
  if (!content) {
    return "";
  }

  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

export function ArtifactPreviewContent({ artifact }: ArtifactPreviewContentProps) {
  if (!artifact) {
    return <ArtifactEmptyState />;
  }

  if (artifact.type === "debug_json") {
    const jsonContent = formatJsonContent(artifact.content);

    return (
      <div className="flex h-full min-h-0 flex-col bg-white">
        <div className="border-b px-4 py-3">
          <div className="text-sm font-semibold">{artifact.title}</div>
          <p className="mt-1 text-xs text-muted-foreground">
            Agent runtime JSON intermediate artifact.
          </p>
        </div>
        <pre className="min-h-0 flex-1 overflow-auto bg-[#fbfbfa] p-4 text-xs leading-5 text-[#27364a]">
          {jsonContent || "{}"}
        </pre>
      </div>
    );
  }

  if (artifact.type === "markdown_report") {
    if (artifact.content) {
      return <MarkdownViewer content={artifact.content} title={artifact.title} />;
    }

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="The Markdown file is ready, but no embeddable content is available."
      />
    );
  }

  if (artifact.type === "html_page") {
    if (artifact.content) {
      return <HtmlViewer content={artifact.content} title={artifact.title} />;
    }

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="The HTML file is ready, but no embeddable page content is available."
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

    return <PptArtifactViewer artifact={artifact} />;
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
        description="The image file is ready, but no embeddable image URL is available."
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

    return (
      <FileArtifactViewer
        artifact={artifact}
        description="The data file is ready, but no tabular preview is available."
      />
    );
  }

  return <ArtifactEmptyState />;
}
