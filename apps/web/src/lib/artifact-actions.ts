import type { Artifact } from "@/types";
import { webAgentApi } from "@/services/adapters";

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

function metadataFileName(artifact: Artifact) {
  const filename = artifact.metadata?.filename;
  return typeof filename === "string" && filename.trim()
    ? filename.trim()
    : undefined;
}

function firstImageUrl(artifact: Artifact) {
  const images = artifact.metadata?.images;
  if (!Array.isArray(images)) {
    return undefined;
  }
  const first = images.find(
    (item): item is { url: string } =>
      typeof item === "object" &&
      item !== null &&
      "url" in item &&
      typeof item.url === "string" &&
      item.url.length > 0,
  );
  return first?.url;
}

export function getArtifactFallbackDownload(artifact: Artifact) {
  const baseName = safeFileName(artifact.title || "artifact") || "artifact";

  if (artifact.type === "markdown_report") {
    return {
      content: artifact.content ?? "",
      fileName: metadataFileName(artifact) ?? `${baseName}.md`,
      mimeType: "text/markdown;charset=utf-8",
    };
  }

  if (artifact.type === "html_page") {
    return {
      content: artifact.content ?? "",
      fileName: metadataFileName(artifact) ?? `${baseName}.html`,
      mimeType: "text/html;charset=utf-8",
    };
  }

  if (artifact.type === "debug_json") {
    return {
      content: artifact.content ?? "",
      fileName: metadataFileName(artifact) ?? `${baseName}.json`,
      mimeType: "application/json;charset=utf-8",
    };
  }

  if (artifact.type === "data_table" || artifact.type === "chart") {
    return {
      content: tableToCsv(artifact),
      fileName: metadataFileName(artifact) ?? `${baseName}.csv`,
      mimeType: "text/csv;charset=utf-8",
    };
  }

  if (artifact.type === "image_result") {
    const imageUrl = firstImageUrl(artifact);
    if (imageUrl?.startsWith("data:image/png")) {
      return {
        content: imageUrl,
        fileName: metadataFileName(artifact) ?? `${baseName}.png`,
        mimeType: "image/png",
      };
    }
    if (imageUrl?.startsWith("data:image/jpeg") || imageUrl?.startsWith("data:image/jpg")) {
      return {
        content: imageUrl,
        fileName: metadataFileName(artifact) ?? `${baseName}.jpg`,
        mimeType: "image/jpeg",
      };
    }
  }

  return {
    content: JSON.stringify(artifact, null, 2),
    fileName: metadataFileName(artifact) ?? `${baseName}.json`,
    mimeType: "application/json;charset=utf-8",
  };
}

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function dataUrlToBlob(dataUrl: string) {
  return fetch(dataUrl).then((response) => response.blob());
}

export async function downloadArtifact(artifact: Artifact) {
  const fallback = getArtifactFallbackDownload(artifact);

  try {
    const blob = await webAgentApi.downloadArtifact(artifact.id);
    saveBlob(blob, metadataFileName(artifact) ?? fallback.fileName);
  } catch {
    const blob = fallback.content.startsWith("data:")
      ? await dataUrlToBlob(fallback.content)
      : new Blob([fallback.content], { type: fallback.mimeType });
    saveBlob(blob, fallback.fileName);
  }
}
