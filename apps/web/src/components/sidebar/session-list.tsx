"use client";

import { SessionItem } from "./session-item";
import { useChatStore, useUiStore } from "@/stores";

export function SessionList() {
  const sessions = useChatStore((state) => state.sessions);
  const loading = useChatStore((state) => state.loading);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const query = useUiStore((state) => state.sessionSearchQuery);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredSessions = normalizedQuery
    ? sessions.filter((session) =>
        session.title.toLowerCase().includes(normalizedQuery),
      )
    : sessions;

  return (
    <section className="space-y-2">
      <h2 className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>History</span>
        <span>{filteredSessions.length}</span>
      </h2>
      <div className="space-y-1">
        {loading ? (
          <div className="rounded-md border border-dashed bg-white/60 px-2 py-3 text-xs text-muted-foreground">
            Loading conversations...
          </div>
        ) : null}
        {!loading && filteredSessions.length === 0 ? (
          <div className="rounded-md border border-dashed bg-white/60 px-2 py-3 text-xs text-muted-foreground">
            No conversations found.
          </div>
        ) : null}
        {filteredSessions.map((session) => (
          <SessionItem
            active={session.id === currentSessionId}
            key={session.id}
            onClick={() => {
              closeArtifactDrawer();
              selectSession(session.id);
            }}
            status={session.status}
            switching={session.id === switchingSessionId}
            title={session.title}
          />
        ))}
      </div>
    </section>
  );
}
