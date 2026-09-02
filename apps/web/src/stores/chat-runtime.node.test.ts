/**
 * File purpose: Verifies terminal Agent Run recovery re-queries authoritative run artifacts.
 * Main declarations: source-contract tests guard polling and SSE terminal refresh behavior.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-runtime.ts", import.meta.url), "utf8");

test("run artifact refresh queries by both session and run", () => {
  assert.match(source, /webAgentApi\.listArtifacts\(sessionId, runId\)/);
});

test("polling and SSE terminal paths refresh run artifacts", () => {
  const calls = source.match(/refreshRunArtifacts\(get, set,/g) ?? [];
  assert.ok(calls.length >= 2);
  assert.match(source, /if \(isTerminalRunStatus\(event\.status\)\)/);
});

test("terminal recovery refreshes persisted conversation messages", () => {
  assert.match(source, /export async function refreshRunMessages/);
  assert.match(source, /refreshRunMessages\(get, set, run\.sessionId\)/);
});

test("workspace loading ignores stale session ids", () => {
  assert.match(
    source,
    /if \(!get\(\)\.sessions\.some\(\(session\) => session\.id === sessionId\)\) \{\s*return;/,
  );
});
