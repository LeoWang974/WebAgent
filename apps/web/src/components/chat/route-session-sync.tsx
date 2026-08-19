/**
 * File purpose: Renders and coordinates the route session sync user-interface feature.
 * Main declarations: RouteSessionSync handles route session sync.
 */

"use client";

import { useLayoutEffect } from "react";
import { useChatStore } from "@/stores";

interface RouteSessionSyncProps {
  sessionId?: string;
}

export function RouteSessionSync({ sessionId }: RouteSessionSyncProps) {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);

  useLayoutEffect(() => {
    const isNavigatingToAnotherSession =
      Boolean(switchingSessionId) && switchingSessionId === currentSessionId;
    if (sessionId && currentSessionId !== sessionId && !isNavigatingToAnotherSession) {
      selectSession(sessionId);
    }
  }, [currentSessionId, selectSession, sessionId, switchingSessionId]);

  return null;
}
