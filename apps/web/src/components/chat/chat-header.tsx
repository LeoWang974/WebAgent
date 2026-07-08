"use client";

import { useChatStore } from "@/stores";
import { Bot } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { getStatusDotClass, getStatusLabelKey } from "@/lib/status";

export function ChatHeader() {
  const { t } = useI18n();
  const sessions = useChatStore((state) => state.sessions);
  const agentRuns = useChatStore((state) => state.agentRuns);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const currentSession = sessions.find(
    (session) => session.id === currentSessionId,
  );
  const currentRun = agentRuns.find((run) => run.sessionId === currentSessionId);
  const status = currentRun?.status ?? currentSession?.status ?? "ready";

  return (
    <div className="flex h-14 items-center justify-between border-b border-[#ededeb] px-5">
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
      <div className="flex items-center gap-1.5 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground">
        <span className={`size-2 rounded-full ${getStatusDotClass(status)}`} />
        {t(getStatusLabelKey(status))}
      </div>
    </div>
  );
}
