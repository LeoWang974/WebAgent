"use client";

import { SessionItem } from "./session-item";
import { useChatStore } from "@/stores";

export function SessionList() {
  const sessions = useChatStore((state) => state.sessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const selectSession = useChatStore((state) => state.selectSession);

  return (
    <section className="space-y-2">
      <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        History
      </h2>
      <div className="space-y-1">
        {sessions.map((session) => (
          <SessionItem
            active={session.id === currentSessionId}
            key={session.id}
            onClick={() => selectSession(session.id)}
            status={session.status}
            title={session.title}
          />
        ))}
      </div>
    </section>
  );
}
