import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./i18n.ts", import.meta.url), "utf8");

function translationValue(key: string) {
  const match = source.match(new RegExp(`\\n    ${key}: "([^"]*)"`));
  return match?.[1];
}

test("Chinese account, run, and admin labels stay valid UTF-8", () => {
  assert.equal(translationValue("accountSecurity"), "账号安全");
  assert.equal(translationValue("accountSecurityDescription"), "更新 WebAgent 账号的登录密码。");
  assert.equal(translationValue("agentRunDetails"), "Agent Run 详情");
  assert.equal(translationValue("agentRunEventsEmpty"), "暂无运行事件");
  assert.equal(translationValue("signIn"), "登录");
  assert.equal(translationValue("signUp"), "注册");
  assert.equal(translationValue("userManagement"), "用户管理");
  assert.equal(translationValue("adminUser"), "管理员");
  assert.equal(translationValue("normalUser"), "普通用户");
});

test("Chinese language pack does not contain known mojibake fragments", () => {
  const zhBlock = source.split('  "en-US": {', 1)[0] ?? "";
  const mojibakeFragments = [
    "璐﹀",
    "鏇存",
    "姝ｅ",
    "杩愯",
    "绠＄",
    "鐧",
    "瀵嗙",
    "�",
  ];

  for (const fragment of mojibakeFragments) {
    assert.equal(zhBlock.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
