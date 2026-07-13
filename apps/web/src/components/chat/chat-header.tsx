"use client";

import { useState } from "react";
import { Bot, Globe2, Lock, Share2, Users, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { getStatusDotClass, getStatusLabelKey } from "@/lib/status";
import { useChatStore } from "@/stores";

export function ChatHeader() {
  const { t } = useI18n();
  const [accessOpen, setAccessOpen] = useState(false);
  const [shareEmail, setShareEmail] = useState("");
  const agentRuns = useChatStore((state) => state.agentRuns);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const sessions = useChatStore((state) => state.sessions);
  const setSessionVisibility = useChatStore((state) => state.setSessionVisibility);
  const shareSession = useChatStore((state) => state.shareSession);
  const sharingSessionId = useChatStore((state) => state.sharingSessionId);
  const unshareSession = useChatStore((state) => state.unshareSession);
  const currentSession = sessions.find(
    (session) => session.id === currentSessionId,
  );
  const currentRun = agentRuns.find((run) => run.sessionId === currentSessionId);
  const status = currentRun?.status ?? currentSession?.status ?? "ready";
  const visibility = currentSession?.visibility ?? "private";
  const AccessIcon = visibility === "public" ? Globe2 : visibility === "shared" ? Users : Lock;
  const accessLabel =
    visibility === "public" ? "公开" : visibility === "shared" ? "共享" : "私有";
  const isSharing = sharingSessionId === currentSessionId;

  return (
    <div className="relative flex h-14 items-center justify-between border-b border-[#ededeb] px-5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-lg border bg-white">
          <Bot className="size-4" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">
            {currentSession?.title ?? t("defaultConversation")}
          </h1>
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
        <div className="absolute right-5 top-12 z-20 w-80 rounded-lg border border-[#deded8] bg-white p-3 text-xs shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">会话权限</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                控制当前对话是否允许其他用户访问。
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
                disabled={isSharing}
                key={item.value}
                onClick={() => setSessionVisibility(currentSession.id, item.value)}
                type="button"
              >
                <item.icon className="size-3.5" />
                {item.label}
              </button>
            ))}
          </div>

          <div className="mt-3 flex gap-1.5">
            <input
              className="min-w-0 flex-1 rounded-md border border-[#deded8] px-2 py-1.5 outline-none focus:border-[#1f1f1d]"
              onChange={(event) => setShareEmail(event.target.value)}
              placeholder="输入用户邮箱"
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
              分享
            </button>
          </div>

          {currentSession.sharedWith?.length ? (
            <div className="mt-3 space-y-1.5">
              {currentSession.sharedWith.map((share) => (
                <div
                  className="flex items-center justify-between rounded-md bg-[#f7f7f5] px-2 py-1.5"
                  key={share.id}
                >
                  <span className="min-w-0 truncate text-muted-foreground">
                    {share.nickname} / {share.email}
                  </span>
                  <button
                    className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-white"
                    disabled={isSharing}
                    onClick={() => unshareSession(currentSession.id, share.id)}
                    type="button"
                  >
                    移除
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
