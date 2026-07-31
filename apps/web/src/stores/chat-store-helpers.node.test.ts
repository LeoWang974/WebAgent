import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-store-helpers.ts", import.meta.url), "utf8");

test("chat helper does not auto-route skills from prompt text", () => {
  assert.equal(source.includes("detectRequestedSkill"), false);
  assert.equal(source.includes("skillAliases"), false, "Unexpected alias routing table");
  for (const marker of ["sn-deep-research", "sn-da", "sn-ppt-workbench"]) {
    assert.equal(source.includes(marker), false, `Unexpected auto-route marker: ${marker}`);
  }
});

test("chat helper labels stay readable Chinese", () => {
  for (const text of ["数据分析", "深度调研", "HTML生成", "PPT生成", "图像生成", "新任务"]) {
    assert.equal(source.includes(text), true, `Missing readable text: ${text}`);
  }
});

test("chat helper does not contain known mojibake fragments", () => {
  for (const fragment of ["閺", "濞", "閻", "鐢", "鏂", "鈧", "锛"]) {
    assert.equal(source.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
