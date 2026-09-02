/**
 * File purpose: Renders and coordinates the route session sync user-interface feature.
 * Main declarations: RouteSessionSync handles route session sync.
 */

"use client";

import { useLayoutEffect } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/stores";
import { resolveRouteSession } from "./route-session-model";

interface RouteSessionSyncProps {
  sessionId?: string;
}

export function RouteSessionSync({ sessionId }: RouteSessionSyncProps) {
  const router = useRouter();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const hydrated = useChatStore((state) => state.hydrated);
  const loading = useChatStore((state) => state.loading);
  const sessions = useChatStore((state) => state.sessions);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);

  useLayoutEffect(() => {
    if (!hydrated || loading) {
      return;
    }

    const resolution = resolveRouteSession({
      currentSessionId,
      routeSessionId: sessionId,
      sessionIds: sessions.map((session) => session.id),
    });
    if (resolution.kind === "redirect") {
      router.replace(resolution.href);
      return;
    }

    const isNavigatingToAnotherSession =
      Boolean(switchingSessionId) && switchingSessionId === currentSessionId;
    if (resolution.kind === "select" && !isNavigatingToAnotherSession) {
      selectSession(resolution.sessionId);
    }
  }, [
    currentSessionId,
    hydrated,
    loading,
    router,
    selectSession,
    sessionId,
    sessions,
    switchingSessionId,
  ]);

  return null;
}
