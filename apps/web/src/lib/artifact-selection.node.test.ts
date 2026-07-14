import assert from "node:assert/strict";
import test from "node:test";
import type { Artifact } from "../types/artifact.ts";
import { shouldSelectCreatedArtifact } from "./artifact-selection.ts";

function artifact(id: string, type: Artifact["type"]): Artifact {
  return {
    id,
    sessionId: "session_1",
    status: "ready",
    title: id,
    type,
  };
}

test("artifact_created selects a higher-priority artifact from the same message", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("report", "markdown_report"),
      eventArtifact: artifact("image", "image_result"),
      selectedBelongsToTargetMessage: true,
    }),
    true,
  );
});

test("artifact_created keeps a higher-priority current artifact from the same message", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("deck", "ppt_deck"),
      eventArtifact: artifact("report", "markdown_report"),
      selectedBelongsToTargetMessage: true,
    }),
    false,
  );
});

test("artifact_created selects the new artifact when current selection is from another message", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("old-deck", "ppt_deck"),
      eventArtifact: artifact("new-report", "markdown_report"),
      selectedBelongsToTargetMessage: false,
    }),
    true,
  );
});
