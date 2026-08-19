import type { Artifact } from "@/types";

export function artifactDisplayPriority(artifact?: Artifact) {
  if (!artifact) {
    return -1;
  }

  const metadata = artifact.metadata ?? {};
  if (metadata.developerOnly === true || metadata.artifactRole === "intermediate") {
    return 0;
  }

  const priorities: Record<Artifact["type"], number> = {
    chart: 60,
    data_table: 60,
    debug_json: 1,
    html_page: 90,
    image_result: 70,
    markdown_report: 75,
    ppt_deck: 100,
  };

  const basePriority = priorities[artifact.type] ?? 0;
  if (artifact.isPrimary === false || metadata.artifactRole === "preview_fallback") {
    return Math.min(basePriority, 20);
  }
  const path = String(metadata.path ?? metadata.originalPath ?? "").toLowerCase();
  const isPrimaryReport =
    artifact.type === "markdown_report" &&
    (artifact.title.toLowerCase() === "report" ||
      artifact.title.includes("报告") ||
      artifact.title.toLowerCase().startsWith("report-") ||
      path.endsWith("/report.md") ||
      path.endsWith("\\report.md") ||
      path.endsWith("/final_report.md") ||
      path.endsWith("\\final_report.md"));

  return isPrimaryReport ? Math.max(basePriority, 80) : basePriority;
}

interface ResolveArtifactSelectionInput {
  currentSelectedArtifact?: Artifact;
  eventArtifact: Artifact;
  selectedBelongsToTargetMessage: boolean;
}

function artifactTime(artifact: Artifact) {
  const value =
    artifact.createdAt ??
    (typeof artifact.metadata?.updatedAt === "string" ? artifact.metadata.updatedAt : undefined);
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sameRun(first?: Artifact, second?: Artifact) {
  return Boolean(first?.runId && second?.runId && first.runId === second.runId);
}

export function compareArtifactsForPreview(first: Artifact, second: Artifact) {
  const priorityDelta = artifactDisplayPriority(second) - artifactDisplayPriority(first);
  if (priorityDelta !== 0) {
    return priorityDelta;
  }
  return artifactTime(second) - artifactTime(first);
}

export function selectPreferredArtifact(
  artifacts: Artifact[],
  sessionId?: string,
): Artifact | undefined {
  return [...artifacts]
    .filter((artifact) => !sessionId || artifact.sessionId === sessionId)
    .sort(compareArtifactsForPreview)[0];
}

export function shouldSelectCreatedArtifact({
  currentSelectedArtifact,
  eventArtifact,
  selectedBelongsToTargetMessage,
}: ResolveArtifactSelectionInput) {
  if (!currentSelectedArtifact) {
    return true;
  }

  const currentPriority = artifactDisplayPriority(currentSelectedArtifact);
  const eventPriority = artifactDisplayPriority(eventArtifact);

  if (sameRun(currentSelectedArtifact, eventArtifact) || selectedBelongsToTargetMessage) {
    return eventPriority > currentPriority;
  }

  return true;
}
