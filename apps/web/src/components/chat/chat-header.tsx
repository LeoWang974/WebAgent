/**
 * File purpose: Renders and coordinates the chat header user-interface feature.
 * Main declarations: copyText handles copy text; ChatHeader handles chat header.
 */

"use client";

import { useState } from "react";
import { Bot, Check, Copy, Globe2, Lock, Pencil, Share2, Users, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { getStatusDotClass, getStatusLabelKey } from "@/lib/status";
import { useChatStore, useUserStore } from "@/stores";

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

export function ChatHeader() {
  const { t } = useI18n();
  const [accessOpen, setAccessOpen] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [shareEmail, setShareEmail] = useState("");
  const [titleDraft, setTitleDraft] = useState("");
  const agentRuns = useChatStore((state) => state.agentRuns);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const sessions = useChatStore((state) => state.sessions);
  const renameSession = useChatStore((state) => state.renameSession);
  const setSessionVisibility = useChatStore((state) => state.setSessionVisibility);
  const shareSession = useChatStore((state) => state.shareSession);
  const sharingSessionId = useChatStore((state) => state.sharingSessionId);
  const unshareSession = useChatStore((state) => state.unshareSession);
  const currentUser = useUserStore((state) => state.user);
  const currentSession = sessions.find((session) => session.id === currentSessionId);
  const currentRun = agentRuns.find((run) => run.sessionId === currentSessionId);
  const status = currentRun?.status ?? currentSession?.status ?? "ready";
  const visibility = currentSession?.visibility ?? "private";
  const AccessIcon = visibility === "public" ? Globe2 : visibility === "shared" ? Users : Lock;
  const accessLabel = visibility === "public" ? "公开" : visibility === "shared" ? "共享" : "私有";
  const isSharing = sharingSessionId === currentSessionId;
  const isOwner = Boolean(currentSession && currentSession.ownerId === currentUser?.id);
  const shareCount = currentSession?.sharedWith?.length ?? 0;
  const shareUrl =
    currentSession && typeof window !== "undefined"
      ? `${window.location.origin}/app/chat/${currentSession.id}`
      : currentSession
        ? `/app/chat/${currentSession.id}`
        : "";

  async function saveTitle() {
    if (!currentSession) {
      return;
    }

    const nextTitle = titleDraft.trim();
    if (nextTitle) {
      await renameSession(currentSession.id, nextTitle);
    }
    setEditingTitle(false);
  }

  async function updateVisibility(nextVisibility: typeof visibility) {
    if (!currentSession) {
      return;
    }

    if (
      nextVisibility === "private" &&
      (visibility !== "private" || shareCount > 0) &&
      !window.confirm("设为私有后，公开链接会失效，已邀请用户也会被移除。确认继续？")
    ) {
      return;
    }

    await setSessionVisibility(currentSession.id, nextVisibility);
  }

  async function copyPublicShareLink() {
    if (!currentSession) {
      return;
    }

    await setSessionVisibility(currentSession.id, "public");
    await copyText(shareUrl);
    setCopiedLink(true);
    window.setTimeout(() => setCopiedLink(false), 1600);
  }

  async function removeSharedUser(userId: string, label: string) {
    if (!currentSession) {
      return;
    }
    if (!window.confirm(`确认取消 ${label} 对当前会话的访问权限？`)) {
      return;
    }
    await unshareSession(currentSession.id, userId);
  }

  return (
    <div className="relative flex h-14 items-center justify-between border-b border-[#ededeb] px-5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-lg border bg-white">
          <Bot className="size-4" />
        </div>
        <div className="min-w-0">
          {editingTitle && currentSession ? (
            <form
              className="flex min-w-0 items-center gap-1"
              onSubmit={(event) => {
                event.preventDefault();
                void saveTitle();
              }}
            >
              <input
                autoFocus
                className="h-7 min-w-0 max-w-[360px] rounded-md border border-[#d8d6cf] bg-white px-2 text-sm font-semibold outline-none focus:border-[#242424]"
                onBlur={() => {
                  void saveTitle();
                }}
                onChange={(event) => setTitleDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    setEditingTitle(false);
                  }
                }}
                value={titleDraft}
              />
              <button
                aria-label="保存会话名"
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2f2ef] hover:text-foreground"
                type="submit"
              >
                <Check className="size-3.5" />
              </button>
            </form>
          ) : (
            <div className="flex min-w-0 items-center gap-1.5">
              <h1 className="truncate text-sm font-semibold">
                {currentSession?.title ?? t("defaultConversation")}
              </h1>
              {currentSession && isOwner ? (
                <button
                  aria-label="重命名会话"
                  className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2f2ef] hover:text-foreground"
                  onClick={() => {
                    setTitleDraft(currentSession.title);
                    setEditingTitle(true);
                  }}
                  title="重命名会话"
                  type="button"
                >
                  <Pencil className="size-3.5" />
                </button>
              ) : null}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            sensenova / {currentSession?.type ?? "chat"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          className="flex items-center gap-1.5 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground hover:bg-[#f7f7f5]"
          disabled={!currentSession}
          onClick={() => setAccessOpen((open) => !open)}
          type="button"
        >
          <AccessIcon className="size-3.5" />
          {accessLabel}
        </button>
        <div className="flex items-center gap-1.5 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground">
          <span className={`size-2 rounded-full ${getStatusDotClass(status)}`} />
          {t(getStatusLabelKey(status))}
        </div>
      </div>

      {accessOpen && currentSession ? (
        <div className="absolute right-5 top-12 z-20 w-96 max-w-[calc(100vw-2rem)] rounded-lg border border-[#deded8] bg-white p-3 text-xs shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">会话权限</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {isOwner
                  ? "控制当前会话是否允许其他用户访问。"
                  : "你正在查看他人的会话，只有会话所有者可以修改权限。"}
              </p>
            </div>
            <button
              className="rounded-md p-1 text-muted-foreground hover:bg-[#f2f2ef]"
              onClick={() => setAccessOpen(false)}
              type="button"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="grid grid-cols-3 gap-1.5">
            {[
              { icon: Lock, label: "私有", value: "private" as const },
              { icon: Users, label: "共享", value: "shared" as const },
              { icon: Globe2, label: "公开", value: "public" as const },
            ].map((item) => (
              <button
                className={`flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 ${
                  visibility === item.value
                    ? "border-[#1f1f1d] bg-[#1f1f1d] text-white"
                    : "border-[#e6e3dc] bg-white text-muted-foreground hover:bg-[#f7f7f5]"
                }`}
                disabled={isSharing || !isOwner}
                key={item.value}
                onClick={() => void updateVisibility(item.value)}
                type="button"
              >
                <item.icon className="size-3.5" />
                {item.label}
              </button>
            ))}
          </div>

          <div className="mt-3 rounded-md border border-[#ece9e1] bg-[#fbfbfa] p-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium text-foreground">分享链接</p>
                <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                  点击后会将会话设为公开，其他已登录用户可通过链接查看。
                </p>
              </div>
              <button
                className="flex h-8 shrink-0 items-center gap-1 rounded-md border bg-white px-2 text-[11px] text-muted-foreground hover:bg-[#f7f7f5] disabled:opacity-50"
                disabled={isSharing || !isOwner}
                onClick={() => void copyPublicShareLink()}
                type="button"
              >
                {copiedLink ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copiedLink ? "已复制" : "复制链接"}
              </button>
            </div>
            <div className="mt-2 truncate rounded border bg-white px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
              {shareUrl}
            </div>
          </div>

          {isOwner ? (
            <div className="mt-3 flex gap-1.5">
              <input
                className="min-w-0 flex-1 rounded-md border border-[#deded8] px-2 py-1.5 outline-none focus:border-[#1f1f1d]"
                onChange={(event) => setShareEmail(event.target.value)}
                placeholder="输入用户邮箱，邀请指定用户"
                type="email"
                value={shareEmail}
              />
              <button
                className="flex items-center gap-1 rounded-md bg-[#1f1f1d] px-2.5 py-1.5 text-white disabled:opacity-50"
                disabled={isSharing || !shareEmail.trim()}
                onClick={async () => {
                  await shareSession(currentSession.id, shareEmail);
                  setShareEmail("");
                }}
                type="button"
              >
                <Share2 className="size-3.5" />
                邀请
              </button>
            </div>
          ) : null}

          <div className="mt-3 rounded-md border border-[#ece9e1]">
            <div className="flex items-center justify-between border-b bg-[#fbfbfa] px-2 py-1.5">
              <span className="font-medium text-foreground">已邀请用户</span>
              <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
                {shareCount}
              </span>
            </div>
            {shareCount ? (
              <div className="max-h-36 overflow-y-auto p-1.5">
                {currentSession.sharedWith?.map((share) => (
                  <div
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-[#f7f7f5]"
                    key={share.id}
                  >
                    <span className="min-w-0 truncate text-muted-foreground">
                      {share.nickname} / {share.email}
                    </span>
                    {isOwner ? (
                      <button
                        className="shrink-0 rounded-md border bg-white px-2 py-1 text-[11px] text-muted-foreground hover:bg-[#fff7f7] hover:text-[#9a4d4d]"
                        disabled={isSharing}
                        onClick={() => void removeSharedUser(share.id, share.email)}
                        type="button"
                      >
                        取消分享
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-2 py-3 text-center text-[11px] text-muted-foreground">
                暂无指定分享用户。
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
