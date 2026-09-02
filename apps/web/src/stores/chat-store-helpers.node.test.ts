/**
 * File purpose: Verifies chat store helpers.node.test behavior and its regression contracts.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-store-helpers.ts", import.meta.url), "utf8");
const sendFlowSource = readFileSync(new URL("./send-message-flow.ts", import.meta.url), "utf8");

test("chat helper does not auto-route skills from prompt text", () => {
  assert.equal(source.includes("detectRequestedSkill"), false);
  assert.equal(source.includes("skillAliases"), false, "Unexpected alias routing table");
  for (const marker of ["sn-deep-research", "sn-da", "sn-ppt-workbench"]) {
    assert.equal(source.includes(marker), false, `Unexpected auto-route marker: ${marker}`);
  }
});

test("message flow forwards the original user content without trimming", () => {
  assert.equal(sendFlowSource.includes("const userContent = content;"), true);
  assert.equal(sendFlowSource.includes("const trimmed = content.trim();"), false);
  assert.ok(
    (sendFlowSource.match(/content: userContent/g) ?? []).length >= 2,
    "Optimistic state and API payload must use the unchanged content",
  );
});

test("automatic titles do not strip prompt intent words", () => {
  for (const semanticPrefix of ["请帮我", "生成", "分析", "写一份", "做一份"]) {
    assert.equal(
      source.includes(semanticPrefix),
      false,
      `Unexpected semantic title cleanup marker: ${semanticPrefix}`,
    );
  }
});

test("chat helper labels stay readable Chinese", () => {
  for (const text of ["新对话", "新任务", "正在工作", "等待运行状态"]) {
    assert.equal(source.includes(text), true, `Missing readable text: ${text}`);
  }
});

test("chat helper does not contain known mojibake fragments", () => {
  for (const fragment of ["锛", "鏂", "璇", "姝", "鐭", "闀", "锟"]) {
    assert.equal(source.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
