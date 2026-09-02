/**
 * File purpose: Resolves route/session synchronization without issuing inaccessible workspace reads.
 * Main declarations: resolveRouteSession determines whether to select a session or repair the URL.
 */

export type RouteSessionResolution =
  | { kind: "idle" }
  | { kind: "redirect"; href: string }
  | { kind: "select"; sessionId: string };

interface RouteSessionInput {
  currentSessionId: string;
  routeSessionId?: string;
  sessionIds: string[];
}

export function resolveRouteSession({
  currentSessionId,
  routeSessionId,
  sessionIds,
}: RouteSessionInput): RouteSessionResolution {
  if (!routeSessionId) {
    return { kind: "idle" };
  }

  if (sessionIds.includes(routeSessionId)) {
    return currentSessionId === routeSessionId
      ? { kind: "idle" }
      : { kind: "select", sessionId: routeSessionId };
  }

  const fallbackSessionId = sessionIds.includes(currentSessionId)
    ? currentSessionId
    : sessionIds[0];
  return {
    kind: "redirect",
    href: fallbackSessionId ? `/app/chat/${fallbackSessionId}` : "/app",
  };
}
