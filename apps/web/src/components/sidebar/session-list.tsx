"use client";

import { SessionItem } from "./session-item";
import { useChatStore, useUiStore } from "@/stores";
import type { Session } from "@/types";
import { useI18n, type TranslationKey } from "@/lib/i18n";

function isSameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function getSessionGroup(session: Session): TranslationKey {
  if (session.pinned) {
    return "pinned";
  }

  const updatedAt = new Date(session.updatedAt);
  const today = new Date();
  const yesterday = new Date();

  yesterday.setDate(today.getDate() - 1);

  if (isSameDay(updatedAt, today)) {
    return "today";
  }

  if (isSameDay(updatedAt, yesterday)) {
    return "yesterday";
  }

  return "earlier";
}

function formatUpdatedLabel(value: string) {
  const updatedAt = new Date(value);

  if (Number.isNaN(updatedAt.getTime())) {
    return "";
  }

  return updatedAt.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function SessionList() {
  const { t } = useI18n();
  const sessions = useChatStore((state) => state.sessions);
  const loading = useChatStore((state) => state.loading);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const toggleSessionPinned = useChatStore((state) => state.toggleSessionPinned);
  const query = useUiStore((state) => state.sessionSearchQuery);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);
  const closeSidebarDrawer = useUiStore((state) => state.closeSidebarDrawer);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredSessions = (
    normalizedQuery
      ? sessions.filter((session) =>
          session.title.toLowerCase().includes(normalizedQuery),
        )
      : sessions
  ).sort((a, b) => {
    if (a.pinned !== b.pinned) {
      return a.pinned ? -1 : 1;
    }

    return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
  });
  const groups: Array<{ key: TranslationKey; sessions: Session[] }> = [
    { key: "pinned", sessions: [] },
    { key: "today", sessions: [] },
    { key: "yesterday", sessions: [] },
    { key: "earlier", sessions: [] },
  ];

  filteredSessions.forEach((session) => {
    groups.find((group) => group.key === getSessionGroup(session))?.sessions.push(session);
  });

  return (
    <section className="space-y-2">
      <h2 className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>{t("history")}</span>
        <span>{filteredSessions.length}</span>
      </h2>
      <div className="space-y-3">
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
        {groups.map((group) =>
          group.sessions.length ? (
            <div className="space-y-1" key={group.key}>
              <div className="px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t(group.key)}
              </div>
              {group.sessions.map((session) => (
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
                    const remainingSessions = filteredSessions.filter(
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
                  onTogglePinned={() => toggleSessionPinned(session.id)}
                  pinned={session.pinned}
                  status={session.status}
                  switching={session.id === switchingSessionId}
                  title={session.title}
                  updatedLabel={formatUpdatedLabel(session.updatedAt)}
                />
              ))}
            </div>
          ) : null,
        )}
      </div>
    </section>
  );
}
