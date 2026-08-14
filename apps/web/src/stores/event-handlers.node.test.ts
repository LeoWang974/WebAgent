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
  assert.match(source, /duplicateStageIndex/);
  assert.match(source, /message\.id\s*!==\s*event\.message\.id/);
});
