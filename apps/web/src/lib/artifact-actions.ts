import type { Artifact } from "@/types";

function safeFileName(value: string) {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

function tableToCsv(artifact: Artifact) {
  const metadata = artifact.metadata as
    | { columns?: string[]; rows?: string[][] }
    | undefined;
  const columns = metadata?.columns ?? [];
  const rows = metadata?.rows ?? [];
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;

  return [columns, ...rows].map((row) => row.map(escape).join(",")).join("\n");
}

export function getArtifactDownload(artifact: Artifact) {
  if (artifact.type === "markdown_report") {
    return {
      content: artifact.content ?? "",
      fileName: `${safeFileName(artifact.title || "artifact")}.md`,
      mimeType: "text/markdown;charset=utf-8",
    };
  }

  if (artifact.type === "data_table" || artifact.type === "chart") {
    return {
      content: tableToCsv(artifact),
      fileName: `${safeFileName(artifact.title || "artifact")}.csv`,
      mimeType: "text/csv;charset=utf-8",
    };
  }

  return {
    content: JSON.stringify(artifact, null, 2),
    fileName: `${safeFileName(artifact.title || "artifact")}.json`,
    mimeType: "application/json;charset=utf-8",
  };
}

export function downloadArtifact(artifact: Artifact) {
  const { content, fileName, mimeType } = getArtifactDownload(artifact);
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
