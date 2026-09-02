/**
 * File purpose: Renders and coordinates the session list user-interface feature.
 * Main declarations: CollapsibleSection handles collapsible section; isSameDay handles is same
 * day; getSessionGroup handles get session group; formatUpdatedLabel handles format updated label;
 * SessionList handles session list.
 */

"use client";

import { ChevronDown, ChevronRight, FolderPlus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import { useChatStore, useUiStore, useUserStore } from "@/stores";
import type { Session } from "@/types";
import { SessionItem } from "./session-item";

interface CollapsibleSectionProps {
  actions?: ReactNode;
  children: ReactNode;
  collapsed: boolean;
  count: number;
  emptyLabel?: string;
  onToggle: () => void;
  title: string;
}

function CollapsibleSection({
  actions,
  children,
  collapsed,
  count,
  emptyLabel,
  onToggle,
  title,
}: CollapsibleSectionProps) {
  const Icon = collapsed ? ChevronRight : ChevronDown;

  return (
    <div className="space-y-1">
      <div className="group flex items-center justify-between px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        <button
          className="flex min-w-0 flex-1 items-center gap-1 rounded-md py-0.5 text-left hover:text-foreground"
          onClick={onToggle}
          title={collapsed ? "展开" : "收起"}
          type="button"
        >
          <Icon className="size-3 shrink-0" />
          <span className="truncate">{title}</span>
          <span className="rounded-full bg-white/70 px-1.5 py-0 text-[9px] font-medium">
            {count}
          </span>
        </button>
        {actions ? <div className="ml-1 flex shrink-0 items-center gap-1">{actions}</div> : null}
      </div>
      {!collapsed && count > 0 ? <div className="space-y-1">{children}</div> : null}
      {!collapsed && count === 0 && emptyLabel ? (
        <div className="rounded-md border border-dashed bg-white/50 px-2 py-2 text-xs text-muted-foreground">
          {emptyLabel}
        </div>
      ) : null}
    </div>
  );
}

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
  const router = useRouter();
  const sessions = useChatStore((state) => state.sessions);
  const folders = useChatStore((state) => state.folders);
  const loading = useChatStore((state) => state.loading);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const currentUserId = useUserStore((state) => state.user?.id);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const switchingSessionId = useChatStore((state) => state.switchingSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const renameSession = useChatStore((state) => state.renameSession);
  const createConversationFolder = useChatStore((state) => state.createConversationFolder);
  const deleteConversationFolder = useChatStore((state) => state.deleteConversationFolder);
  const moveSessionToFolder = useChatStore((state) => state.moveSessionToFolder);
  const toggleSessionPinned = useChatStore((state) => state.toggleSessionPinned);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [folderName, setFolderName] = useState("");
  const query = useUiStore((state) => state.sessionSearchQuery);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);
  const closeSidebarDrawer = useUiStore((state) => state.closeSidebarDrawer);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredSessions = (
    normalizedQuery
      ? sessions.filter((session) => session.title.toLowerCase().includes(normalizedQuery))
      : sessions
  ).sort((a, b) => {
    if (a.pinned !== b.pinned) {
      return a.pinned ? -1 : 1;
    }

    return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
  });
  const publicSessions = filteredSessions.filter((session) => session.visibility === "public");
  const sessionsByFolder = folders.map((folder) => ({
    folder,
    key: `folder:${folder.id}`,
    sessions: filteredSessions.filter(
      (session) => session.folderId === folder.id && session.visibility !== "public",
    ),
  }));
  const groups: Array<{ key: TranslationKey; sessions: Session[] }> = [
    { key: "pinned", sessions: [] },
    { key: "today", sessions: [] },
    { key: "yesterday", sessions: [] },
    { key: "earlier", sessions: [] },
  ];

  filteredSessions.forEach((session) => {
    if (session.visibility === "public" || session.folderId) {
      return;
    }
    groups.find((group) => group.key === getSessionGroup(session))?.sessions.push(session);
  });

  function isCollapsed(key: string) {
    return collapsedSections[key] ?? false;
  }

  function toggleSection(key: string) {
    setCollapsedSections((current) => ({
      ...current,
      [key]: !(current[key] ?? false),
    }));
  }

  function renderSession(session: Session) {
    return (
      <SessionItem
        active={session.id === currentSessionId}
        canManage={!session.ownerId || session.ownerId === currentUserId}
        folderId={session.folderId}
        folders={folders}
        href={`/app/chat/${session.id}`}
        key={session.id}
        onClick={() => {
          closeArtifactDrawer();
          closeSidebarDrawer();
          selectSession(session.id);
        }}
        onDelete={async () => {
          const deleted = await deleteSession(session.id);
          if (!deleted) {
            return;
          }
          closeArtifactDrawer();
          closeSidebarDrawer();

          if (session.id === currentSessionId) {
            const nextSessionId = useChatStore.getState().currentSessionId;
            router.replace(nextSessionId ? `/app/chat/${nextSessionId}` : "/app");
          }
        }}
        onMoveToFolder={(folderId) => moveSessionToFolder(session.id, folderId)}
        onRename={(title) => renameSession(session.id, title)}
        onTogglePinned={() => toggleSessionPinned(session.id)}
        pinned={session.pinned}
        status={session.status}
        switching={session.id === switchingSessionId}
        title={session.title}
        updatedLabel={formatUpdatedLabel(session.updatedAt)}
      />
    );
  }

  return (
    <section className="space-y-2">
      <h2 className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>{t("history")}</span>
        <span className="flex items-center gap-1">
          {filteredSessions.length}
          <button
            className="flex size-5 items-center justify-center rounded-md hover:bg-white hover:text-foreground"
            onClick={() => setCreatingFolder((value) => !value)}
            title="新建目录"
            type="button"
          >
            <FolderPlus className="size-3.5" />
          </button>
        </span>
      </h2>
      <div className="space-y-3">
        {creatingFolder ? (
          <form
            className="flex gap-1 px-1"
            onSubmit={(event) => {
              event.preventDefault();
              void createConversationFolder(folderName).then(() => {
                setFolderName("");
                setCreatingFolder(false);
              });
            }}
          >
            <input
              autoFocus
              className="min-w-0 flex-1 rounded-md border bg-white px-2 py-1 text-xs outline-none focus:border-[#242424]"
              onChange={(event) => setFolderName(event.target.value)}
              placeholder="目录名称"
              value={folderName}
            />
            <button
              className="rounded-md border bg-white px-2 text-xs hover:bg-muted"
              disabled={!folderName.trim()}
              type="submit"
            >
              保存
            </button>
          </form>
        ) : null}
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
        {!loading && filteredSessions.length > 0 ? (
          <>
            <CollapsibleSection
              collapsed={isCollapsed("public")}
              count={publicSessions.length}
              emptyLabel="暂无公开对话"
              onToggle={() => toggleSection("public")}
              title="公开对话"
            >
              {publicSessions.map(renderSession)}
            </CollapsibleSection>
            {sessionsByFolder.map(({ folder, key, sessions: folderSessions }) => (
              <CollapsibleSection
                actions={
                  <button
                    className="flex size-5 items-center justify-center rounded-md opacity-0 hover:bg-white hover:text-red-600 group-hover:opacity-100"
                    onClick={() => void deleteConversationFolder(folder.id)}
                    title="删除目录"
                    type="button"
                  >
                    <Trash2 className="size-3" />
                  </button>
                }
                collapsed={isCollapsed(key)}
                count={folderSessions.length}
                emptyLabel="暂无会话"
                key={folder.id}
                onToggle={() => toggleSection(key)}
                title={folder.name}
              >
                {folderSessions.map(renderSession)}
              </CollapsibleSection>
            ))}
            {groups.map((group) =>
              group.sessions.length ? (
                <CollapsibleSection
                  collapsed={isCollapsed(group.key)}
                  count={group.sessions.length}
                  key={group.key}
                  onToggle={() => toggleSection(group.key)}
                  title={t(group.key)}
                >
                  {group.sessions.map(renderSession)}
                </CollapsibleSection>
              ) : null,
            )}
          </>
        ) : null}
      </div>
    </section>
  );
}
