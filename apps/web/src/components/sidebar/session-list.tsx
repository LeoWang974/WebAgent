"use client";

import { SessionItem } from "./session-item";
import { useChatStore, useUiStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

export function SessionList() {
  const { t } = useI18n();
  const sessions = useChatStore((state) => state.sessions);
  const loading = useChatStore((state) => state.loading);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const query = useUiStore((state) => state.sessionSearchQuery);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);
  const closeSidebarDrawer = useUiStore((state) => state.closeSidebarDrawer);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredSessions = normalizedQuery
    ? sessions.filter((session) =>
        session.title.toLowerCase().includes(normalizedQuery),
      )
    : sessions;

  return (
    <section className="space-y-2">
      <h2 className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>{t("history")}</span>
        <span>{filteredSessions.length}</span>
      </h2>
      <div className="space-y-1">
        {loading ? (
          <div className="rounded-md border border-dashed bg-white/60 px-2 py-3 text-xs text-muted-foreground">
            {t("loadingConversations")}
          </div>
        ) : null}
        {!loading && filteredSessions.length === 0 ? (
          <div className="rounded-md border border-dashed bg-white/60 px-2 py-3 text-xs text-muted-foreground">
            {t("noConversations")}
          </div>
        ) : null}
        {filteredSessions.map((session) => (
          <SessionItem
            active={session.id === currentSessionId}
            href={`/app/chat/${session.id}`}
            key={session.id}
            onClick={() => {
              closeArtifactDrawer();
              closeSidebarDrawer();
              selectSession(session.id);
            }}
            onDelete={() => {
              const remainingSessions = sessions.filter(
                (item) => item.id !== session.id,
              );
              const nextSessionId = remainingSessions[0]?.id;

              closeArtifactDrawer();
              closeSidebarDrawer();
              deleteSession(session.id);

              if (session.id === currentSessionId) {
                window.location.assign(
                  nextSessionId ? `/app/chat/${nextSessionId}` : "/app",
                );
              }
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
