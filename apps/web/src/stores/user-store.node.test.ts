/**
 * File purpose: Verifies account changes cannot reuse workspace state from another user.
 * Main declarations: login and registration reset test protects user-scoped store isolation.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./user-store.ts", import.meta.url), "utf8");

test("login and registration reset user-scoped workspace state", () => {
  const resets = source.match(/useChatStore\.getState\(\)\.resetWorkspace\(\)/g) ?? [];
  const settingsResets = source.match(/useSettingsStore\.getState\(\)\.reset\(\)/g) ?? [];

  assert.ok(resets.length >= 3, "login, registration, and logout must reset chat state");
  assert.ok(settingsResets.length >= 3, "login, registration, and logout must reset settings");
});
