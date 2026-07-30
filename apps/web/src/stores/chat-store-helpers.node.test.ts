import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-store-helpers.ts", import.meta.url), "utf8");

test("chat helper only routes when skill is explicitly selected", () => {
  assert.equal(source.includes("return explicitSkillKey;"), true);
  for (const marker of ["sn-deep-research", "sn-da", "sn-ppt-workbench"]) {
    assert.equal(source.includes(marker), false, `Unexpected auto-route marker: ${marker}`);
  }
  assert.equal(source.includes("skillAliases"), false, "Unexpected alias routing table");
});

test("chat helper labels stay readable Chinese", () => {
  for (const text of ["数据分析", "深度调研", "HTML生成", "PPT生成", "图像生成", "新任务"]) {
    assert.equal(source.includes(text), true, `Missing readable text: ${text}`);
  }
});

test("chat helper does not contain known mojibake fragments", () => {
  for (const fragment of [
    "\u95ba\u4f7a\u5897",
    "\u6fde\uff45\u5d2c",
    "\u95bb\u3222\u5590",
    "\u95ba\u509e",
    "\u6fee\u6fd3\u7d7d",
    "\u95bf\u6d98\u77bc",
    "\u93c1\u7248\u5d41",
    "\u5a23\u535e\u5bb3",
    "\u59dd\uff45\u6e6a",
  ]) {
    assert.equal(source.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
