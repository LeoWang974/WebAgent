import assert from "node:assert/strict";
import test from "node:test";
import type { Artifact } from "../types/artifact.ts";
import {
  selectPreferredArtifact,
  shouldSelectCreatedArtifact,
} from "./artifact-selection.ts";

function artifact(
  id: string,
  type: Artifact["type"],
  input: Partial<Artifact> = {},
): Artifact {
  return {
    id,
    sessionId: "session_1",
    status: "ready",
    title: id,
    type,
    ...input,
  };
}

test("artifact_created selects a higher-priority artifact from the same run", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("report", "markdown_report", { runId: "run_1" }),
      eventArtifact: artifact("deck", "ppt_deck", { runId: "run_1" }),
      selectedBelongsToTargetMessage: true,
    }),
    true,
  );
});

test("artifact_created keeps a higher-priority current artifact from the same run", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("deck", "ppt_deck", { runId: "run_1" }),
      eventArtifact: artifact("report", "markdown_report", { runId: "run_1" }),
      selectedBelongsToTargetMessage: true,
    }),
    false,
  );
});

test("artifact_created does not let debug JSON steal focus from user artifacts", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("report", "markdown_report"),
      eventArtifact: artifact("briefing", "debug_json"),
      selectedBelongsToTargetMessage: true,
    }),
    false,
  );
});

test("artifact_created does not let intermediate artifacts steal focus", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("deck", "ppt_deck"),
      eventArtifact: artifact("plan", "markdown_report", {
        metadata: { artifactRole: "intermediate", developerOnly: true },
      }),
      selectedBelongsToTargetMessage: true,
    }),
    false,
  );
});

test("artifact_created keeps current artifact when same-run priority ties", () => {
  assert.equal(
    shouldSelectCreatedArtifact({
      currentSelectedArtifact: artifact("report", "markdown_report", { runId: "run_1" }),
      eventArtifact: artifact("skill-doc", "markdown_report", { runId: "run_1" }),
      selectedBelongsToTargetMessage: false,
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

test("selectPreferredArtifact uses preview priority before recency", () => {
  const selected = selectPreferredArtifact([
    artifact("debug", "debug_json", { createdAt: "2026-07-23T12:00:00Z" }),
    artifact("report", "markdown_report", {
      createdAt: "2026-07-23T11:00:00Z",
      metadata: { path: "/home/demo/report.md" },
      title: "report",
    }),
    artifact("deck", "ppt_deck", { createdAt: "2026-07-23T10:00:00Z" }),
  ]);

  assert.equal(selected?.id, "deck");
});

test("ppt deck wins over newer HTML slide fallback", () => {
  const selected = selectPreferredArtifact([
    artifact("page_001", "html_page", {
      createdAt: "2026-07-23T12:00:00Z",
      isPrimary: false,
      metadata: { artifactRole: "preview_fallback" },
    }),
    artifact("deck", "ppt_deck", { createdAt: "2026-07-23T11:00:00Z", isPrimary: true }),
  ]);

  assert.equal(selected?.id, "deck");
});
