import type { Artifact } from "@/types";

export function artifactDisplayPriority(artifact?: Artifact) {
  if (!artifact) {
    return -1;
  }

  const priorities: Record<Artifact["type"], number> = {
    chart: 30,
    data_table: 20,
    html_page: 40,
    image_result: 90,
    markdown_report: 10,
    ppt_deck: 80,
  };

  return priorities[artifact.type] ?? 0;
}

interface ResolveArtifactSelectionInput {
  currentSelectedArtifact?: Artifact;
  eventArtifact: Artifact;
  selectedBelongsToTargetMessage: boolean;
}

export function shouldSelectCreatedArtifact({
  currentSelectedArtifact,
  eventArtifact,
  selectedBelongsToTargetMessage,
}: ResolveArtifactSelectionInput) {
  return (
    !currentSelectedArtifact ||
    !selectedBelongsToTargetMessage ||
    artifactDisplayPriority(eventArtifact) >= artifactDisplayPriority(currentSelectedArtifact)
  );
}
