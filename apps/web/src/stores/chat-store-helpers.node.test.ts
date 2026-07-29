import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./chat-store-helpers.ts", import.meta.url), "utf8");

test("chat helper skill routing requires explicit markers", () => {
  for (const marker of ["sn-deep-research", "sn-da", "sn-ppt-workbench", "u1_image"]) {
    assert.equal(source.includes(marker), true, `Missing explicit marker: ${marker}`);
  }
  for (const genericAlias of ['"ppt"', '"调研"', '"研究报告"', '"生成图片"']) {
    assert.equal(source.includes(genericAlias), false, `Unexpected generic alias: ${genericAlias}`);
  }
});

test("chat helper labels stay readable Chinese", () => {
  for (const text of ["数据分析", "深度调研", "PPT生成", "图像生成", "新任务"]) {
    assert.equal(source.includes(text), true, `Missing readable text: ${text}`);
  }
});

test("chat helper does not contain known mojibake fragments", () => {
  for (const fragment of ["濞ｅ崬瀹", "閺佺増宓", "閻㈢喐鍨", "濮濓絽婀", "閿", "閺傛澘"]) {
    assert.equal(source.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
