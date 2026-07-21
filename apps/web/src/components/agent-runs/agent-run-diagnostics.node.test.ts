import assert from "node:assert/strict";
import test from "node:test";
import type { AgentRun, AgentRunEvent } from "../../types/agent-run.ts";
import { buildRunDiagnosticViewModel } from "./agent-run-diagnostics.ts";

function run(): AgentRun {
  return {
    adapterKey: "openclaw",
    id: "run_1",
    progress: 80,
    sessionId: "session_1",
    startedAt: "2026-07-21T10:00:00.000Z",
    status: "failed",
    steps: [],
    title: "OpenClaw run",
  };
}

function event(eventType: string, label: string, payload?: Record<string, unknown>): AgentRunEvent {
  return {
    eventType,
    payload,
    progress: 80,
    runId: "run_1",
    status: eventType === "diagnostic" ? "failed" : "running",
    step: {
      id: `${eventType}_${label}`,
      label,
      status: eventType === "diagnostic" ? "failed" : "completed",
      timestamp: "2026-07-21T10:00:01.000Z",
    },
  };
}

test("OpenClaw diagnostic view model exposes exit code, stderr tail, and last stage", () => {
  const stage = event("stage_started", "Writing final report");
  const diagnosticEvent = event("diagnostic", "Agent run failed", {
    artifactDiscovery: { discovered_count: 0 },
    runtimeDiagnostics: {
      exitCode: 134,
      lastStage: "Exporting PPTX",
      stderrTail: "OpenClaw gateway failed while exporting deck",
      stdoutTail: "last stdout line",
    },
  });

  const result = buildRunDiagnosticViewModel(diagnosticEvent, run(), [
    stage,
    diagnosticEvent,
  ]);

  assert.equal(result.adapterLabel, "OpenClaw");
  assert.equal(result.exitCode, 134);
  assert.equal(result.lastStage, "Exporting PPTX");
  assert.equal(result.stderrTail, "OpenClaw gateway failed while exporting deck");
  assert.equal(result.stdoutTail, "last stdout line");
  assert.deepEqual(result.artifactDiscovery, { discovered_count: 0 });
});

test("diagnostic view model falls back to latest stage when adapter omits lastStage", () => {
  const stage = event("stage_started", "Generating image artifact");
  const diagnosticEvent = event("diagnostic", "Agent run failed", {
    runtimeDiagnostics: {
      exit_code: 2,
      stderr_tail: "image backend unavailable",
    },
  });

  const result = buildRunDiagnosticViewModel(diagnosticEvent, run(), [
    stage,
    diagnosticEvent,
  ]);

  assert.equal(result.exitCode, 2);
  assert.equal(result.lastStage, "Generating image artifact");
  assert.equal(result.stderrTail, "image backend unavailable");
});
