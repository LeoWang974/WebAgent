import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./i18n.ts", import.meta.url), "utf8");

function translationValue(key: string) {
  const match = source.match(new RegExp(`\\n    ${key}: "([^"]*)"`));
  if (!match?.[1]) {
    return undefined;
  }
  return JSON.parse(`"${match[1]}"`) as string;
}

test("Chinese account, run, and admin labels stay valid UTF-8", () => {
  assert.equal(translationValue("accountSecurity"), "\u8d26\u53f7\u5b89\u5168");
  assert.equal(
    translationValue("accountSecurityDescription"),
    "\u66f4\u65b0 WebAgent \u8d26\u53f7\u7684\u767b\u5f55\u5bc6\u7801\u3002",
  );
  assert.equal(translationValue("agentRunDetails"), "Agent Run \u8be6\u60c5");
  assert.equal(translationValue("agentRunEventsEmpty"), "\u6682\u65e0\u8fd0\u884c\u4e8b\u4ef6");
  assert.equal(translationValue("signIn"), "\u767b\u5f55");
  assert.equal(translationValue("signUp"), "\u6ce8\u518c");
  assert.equal(translationValue("userManagement"), "\u7528\u6237\u7ba1\u7406");
  assert.equal(translationValue("adminUser"), "\u7ba1\u7406\u5458");
  assert.equal(translationValue("normalUser"), "\u666e\u901a\u7528\u6237");
});

test("Chinese language pack does not contain known mojibake fragments", () => {
  const zhBlock = source.split('  "en-US": {', 1)[0] ?? "";
  const mojibakeFragments = [
    "\u7487\ufe3d\u5111",
    "\u93c6\u509b",
    "\u9427\u8be7",
    "\u5a09",
    "\u7ee0\uff05",
    "\u7015",
    "\u5f00\u53d1\u8005",
    "\u7528\u6237",
    "\ufffd",
  ];

  for (const fragment of mojibakeFragments) {
    assert.equal(zhBlock.includes(fragment), false, `Unexpected mojibake: ${fragment}`);
  }
});
