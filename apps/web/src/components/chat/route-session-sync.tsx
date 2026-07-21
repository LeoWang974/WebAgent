"use client";

import { useLayoutEffect } from "react";
import { useChatStore } from "@/stores";

interface RouteSessionSyncProps {
  sessionId?: string;
}

export function RouteSessionSync({ sessionId }: RouteSessionSyncProps) {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const selectSession = useChatStore((state) => state.selectSession);

  useLayoutEffect(() => {
    if (sessionId && currentSessionId !== sessionId) {
      selectSession(sessionId);
    }
  }, [currentSessionId, selectSession, sessionId]);

  return null;
}
