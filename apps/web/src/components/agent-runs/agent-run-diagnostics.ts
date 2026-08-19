/**
 * File purpose: Renders and coordinates the agent run diagnostics user-interface feature.
 * Main declarations: asRecord handles as record; getText handles get text; adapterLabel handles
 * adapter label; latestStage handles latest stage; buildRunDiagnosticViewModel handles build run
 * diagnostic view model.
 */

import type { AgentRun, AgentRunEvent } from "@/types";

export interface RunDiagnosticViewModel {
  adapterLabel: string;
  artifactDiscovery: Record<string, unknown>;
  exitCode?: unknown;
  lastStage?: string;
  rawLogPath?: string;
  stderrTail?: string;
  stdoutTail?: string;
}

const adapterLabels: Record<string, string> = {
  hermes: "Hermes",
};

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function getText(value: unknown) {
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function adapterLabel(adapterKey?: string) {
  return adapterKey ? (adapterLabels[adapterKey] ?? adapterKey) : "-";
}

export function latestStage(events: AgentRunEvent[]) {
  return [...events]
    .reverse()
    .find((event) => event.eventType !== "diagnostic" && event.step.label)?.step.label;
}

export function buildRunDiagnosticViewModel(
  event: AgentRunEvent,
  run: AgentRun,
  events: AgentRunEvent[],
): RunDiagnosticViewModel {
  const payload = asRecord(event.payload);
  const runtimeDiagnostics = asRecord(
    payload.runtimeDiagnostics ?? payload.hermesDiagnostics,
  );

  return {
    adapterLabel: adapterLabel(run.adapterKey),
    artifactDiscovery: asRecord(payload.artifactDiscovery),
    exitCode: runtimeDiagnostics.exit_code ?? runtimeDiagnostics.exitCode,
    lastStage:
      getText(runtimeDiagnostics.last_stage ?? runtimeDiagnostics.lastStage) ??
      latestStage(events),
    rawLogPath: getText(runtimeDiagnostics.raw_log_path ?? runtimeDiagnostics.rawLogPath),
    stderrTail: getText(runtimeDiagnostics.stderr_tail ?? runtimeDiagnostics.stderrTail),
    stdoutTail: getText(runtimeDiagnostics.stdout_tail ?? runtimeDiagnostics.stdoutTail),
  };
}
