/**
 * File purpose: Verifies sse parser.node.test behavior and its regression contracts.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { parseSseEvents, splitSseBuffer } from "./sse-parser.ts";

test("parseSseEvents keeps valid events and ignores malformed JSON", () => {
  const originalWarn = console.warn;
  let warningCount = 0;
  console.warn = () => {
    warningCount += 1;
  };

  try {
    const events = parseSseEvents(
      [
        'event: assistant_delta\ndata: {"content":"hello","messageId":"m1"}',
        "event: assistant_delta\ndata: {bad json",
        'event: artifact_created\ndata: {"artifact":{"id":"a1"}}',
      ].join("\n\n"),
    );

    assert.deepEqual(events, [
      {
        data: { content: "hello", messageId: "m1" },
        type: "assistant_delta",
      },
      {
        data: { artifact: { id: "a1" } },
        type: "artifact_created",
      },
    ]);
    assert.equal(warningCount, 1);
  } finally {
    console.warn = originalWarn;
  }
});

test("splitSseBuffer keeps incomplete trailing events until the next chunk", () => {
  const first = splitSseBuffer(
    'event: assistant_delta\ndata: {"content":"first"}\n\n' +
      'event: assistant_done\ndata: {"message":{"id":"m1"}}',
  );

  assert.deepEqual(first.events, [
    {
      data: { content: "first" },
      type: "assistant_delta",
    },
  ]);
  assert.equal(first.remainingBuffer, 'event: assistant_done\ndata: {"message":{"id":"m1"}}');

  const flushed = parseSseEvents(first.remainingBuffer);
  assert.deepEqual(flushed, [
    {
      data: { message: { id: "m1" } },
      type: "assistant_done",
    },
  ]);
});
