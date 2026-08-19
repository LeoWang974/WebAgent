/**
 * File purpose: Verifies agent status model.node.test behavior and its regression contracts.
 * Main declarations: run handles run.
 */

import assert from "node:assert/strict";
import test from "node:test";
import type { AgentRun } from "../../types/agent-run.ts";
import { isAgentRunActive, selectAgentStatusRun } from "./agent-status-model.ts";

function run(id: string, status: AgentRun["status"], sessionId = "session_1"): AgentRun {
  return {
    id,
    progress: status === "completed" ? 100 : 42,
    sessionId,
    startedAt: new Date().toISOString(),
    status,
    steps: [],
    title: id,
  };
}

test("selectAgentStatusRun prefers the active run for the current session", () => {
  assert.equal(
    selectAgentStatusRun(
      [
        run("completed_run", "completed"),
        run("running_run", "running"),
        run("other_session_run", "running", "session_2"),
      ],
      "session_1",
    )?.id,
    "running_run",
  );
});

test("selectAgentStatusRun falls back to the latest session run when no active run exists", () => {
  assert.equal(
    selectAgentStatusRun([run("failed_run", "failed"), run("done_run", "completed")], "session_1")
      ?.id,
    "failed_run",
  );
});

test("isAgentRunActive treats disconnected as a terminal status", () => {
  assert.equal(isAgentRunActive(run("stale", "disconnected")), false);
  assert.equal(isAgentRunActive(run("active", "rendering")), true);
});
