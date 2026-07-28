import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-store-helpers.ts", import.meta.url), "utf8");

test("chat helper skill aliases and labels stay readable Chinese", () => {
  for (const text of [
    "深度调研",
    "研究报告",
    "数据分析",
    "表格分析",
    "幻灯片",
    "演示文稿",
    "图像生成",
    "新对话",
    "正在工作，等待运行状态",
  ]) {
    assert.equal(source.includes(text), true, `Missing readable text: ${text}`);
  }
});

test("chat helper does not contain known mojibake fragments", () => {
  for (const fragment of ["娣卞害", "鏁版嵁", "鐢熸垚", "姝ｅ湪", "锛", "鏂板"]) {
    assert.equal(source.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
