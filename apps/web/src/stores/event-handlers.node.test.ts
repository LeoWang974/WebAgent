/**
 * File purpose: Verifies event handlers.node.test behavior and its regression contracts.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./event-handlers.ts", import.meta.url), "utf8");
const sendMessageFlowSource = readFileSync(
  new URL("./send-message-flow.ts", import.meta.url),
  "utf8",
);

test("stream assistant delta dedupes messages already inserted by run events", () => {
  assert.match(source, /existingMessageIndex\s*=\s*state\.messages\.findIndex/);
  assert.match(source, /message\.id\s*===\s*event\.messageId/);
  assert.match(source, /existingMessageIndex\s*>=\s*0/);
});

test("stream assistant delta dedupes repeated run steps", () => {
  assert.match(source, /appendAssistantStepOnce/);
  assert.match(source, /normalizedSteps\.some\(\(step\)\s*=>\s*step\.id\s*===\s*messageId\)/);
});

test("assistant done removes a duplicate terminal stage bubble", () => {
  assert.match(source, /normalizeMessageContent\(event\.message\.content\)/);
  assert.match(source, /duplicateStageEntry/);
  assert.match(source, /message\.id\s*!==\s*event\.message\.id/);
});

test("assistant done preserves the previous wait interval when terminal timestamps collapse", () => {
  assert.match(source, /completedMessageWaitStartedAt/);
  assert.match(source, /deliveredAtMs\s*-\s*explicitStartedAtMs\s*>=\s*1000/);
  assert.match(source, /previousMessage\?\.createdAt\s*\?\?\s*message\.waitStartedAt/);
  assert.match(source, /duplicateStageEntry\.message\.createdAt/);
  assert.match(
    source,
    /completedMessageWaitStartedAt\(\s*state\.messages,\s*duplicateStageEntry\.message/,
  );
});

test("message flow subscribes to persisted run events as soon as the backend run starts", () => {
  assert.match(sendMessageFlowSource, /event\.type\s*===\s*"run_started"/);
  assert.match(
    sendMessageFlowSource,
    /subscribeAgentRunEvents\(get,\s*set,\s*event\.runId\)/,
  );
});

test("run events without a message id still reach the conversation bubbles", () => {
  assert.match(source, /event\.step\?\.id/);
  assert.match(source, /run_event_\$\{event\.runId\}_\$\{event\.step\.id\}/);
  assert.match(source, /const messageId =/);
});

test("run event handling recovers a run that was not loaded before its first event", () => {
  assert.match(source, /recoverRunFromPendingMessage/);
  assert.match(source, /if \(!eventRun && recoveredRun\)/);
  assert.match(source, /nextAgentRuns\.push\(recoveredRun\)/);
});

test("completed runs cannot regress after a late cancelled or disconnected event", () => {
  assert.match(source, /mergeRunStatus\(run\.status, event\.status\)/);
  assert.match(source, /currentStatus === "completed" && incomingStatus !== "completed"/);
  assert.match(source, /isTerminalRunStatus\(currentStatus\) && !isTerminalRunStatus\(incomingStatus\)/);
});

test("terminal run events still materialize their content before pending cleanup", () => {
  assert.match(source, /const eventMessages = applyRunningAgentRunEventMessages/);
  assert.match(source, /messages: terminal\s*\? removePendingMessagesForRun\(\{ \.\.\.nextState, messages: eventMessages \}/);
});
