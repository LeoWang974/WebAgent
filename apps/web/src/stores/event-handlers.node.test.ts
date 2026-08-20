/**
 * File purpose: Verifies event handlers.node.test behavior and its regression contracts.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./event-handlers.ts", import.meta.url), "utf8");

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
