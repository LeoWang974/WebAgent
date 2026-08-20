/**
 * File purpose: Renders a downloadable artifact when an inline preview is unavailable.
 * Main declarations: iconForType selects the file icon; formatBytes formats file size;
 * FileArtifactViewer renders metadata, an optional recovery action, and download control.
 */

"use client";

import { Download, FileArchive, FileImage, FileText, Presentation, RotateCcw } from "lucide-react";
import { downloadArtifact } from "@/lib/artifact-actions";
import type { Artifact } from "@/types";

interface FileArtifactViewerProps {
  actionLabel?: string;
  artifact: Artifact;
  description: string;
  onAction?: () => void;
}

function iconForType(type: Artifact["type"]) {
  if (type === "ppt_deck") {
    return <Presentation className="size-5" />;
  }
  if (type === "image_result") {
    return <FileImage className="size-5" />;
  }
  if (type === "html_page" || type === "markdown_report") {
    return <FileText className="size-5" />;
  }
  return <FileArchive className="size-5" />;
}

function formatBytes(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return undefined;
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function FileArtifactViewer({
  actionLabel,
  artifact,
  description,
  onAction,
}: FileArtifactViewerProps) {
  const filename =
    typeof artifact.metadata?.filename === "string"
      ? artifact.metadata.filename
      : artifact.title;
  const size = formatBytes(artifact.metadata?.size);

  return (
    <div className="rounded-lg border bg-white p-5 shadow-sm">
      <div className="flex items-start gap-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-lg border bg-[#f7f7f5] text-muted-foreground">
          {iconForType(artifact.type)}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{artifact.title}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
          <div className="mt-3 grid gap-1 text-xs text-muted-foreground">
            <div className="truncate">文件：{filename}</div>
            {size ? <div>大小：{size}</div> : null}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {onAction ? (
              <button
                className="inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm hover:bg-muted"
                onClick={onAction}
                type="button"
              >
                <RotateCcw className="size-4" />
                {actionLabel ?? "重试"}
              </button>
            ) : null}
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm hover:bg-muted"
              onClick={() => void downloadArtifact(artifact)}
              type="button"
            >
              <Download className="size-4" />
              下载原文件
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
