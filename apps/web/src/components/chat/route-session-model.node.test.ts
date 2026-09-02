/**
 * File purpose: Verifies stale and accessible conversation routes resolve without permission errors.
 * Main declarations: route resolution tests cover selection, repair, and clean workspace states.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { resolveRouteSession } from "./route-session-model.ts";

test("selects an accessible route session", () => {
  assert.deepEqual(
    resolveRouteSession({
      currentSessionId: "session-a",
      routeSessionId: "session-b",
      sessionIds: ["session-a", "session-b"],
    }),
    { kind: "select", sessionId: "session-b" },
  );
});

test("repairs a deleted or inaccessible route using the current session", () => {
  assert.deepEqual(
    resolveRouteSession({
      currentSessionId: "session-b",
      routeSessionId: "deleted-session",
      sessionIds: ["session-a", "session-b"],
    }),
    { kind: "redirect", href: "/app/chat/session-b" },
  );
});

test("returns to the empty workspace when no accessible sessions remain", () => {
  assert.deepEqual(
    resolveRouteSession({
      currentSessionId: "deleted-session",
      routeSessionId: "deleted-session",
      sessionIds: [],
    }),
    { kind: "redirect", href: "/app" },
  );
});
