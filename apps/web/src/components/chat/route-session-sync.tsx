"use client";

import { useEffect } from "react";
import { useChatStore } from "@/stores";

interface RouteSessionSyncProps {
  sessionId?: string;
}

export function RouteSessionSync({ sessionId }: RouteSessionSyncProps) {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const hydrated = useChatStore((state) => state.hydrated);
  const selectSession = useChatStore((state) => state.selectSession);

  useEffect(() => {
    if (hydrated && sessionId && currentSessionId !== sessionId) {
      selectSession(sessionId);
    }
  }, [currentSessionId, hydrated, selectSession, sessionId]);

  return null;
}

