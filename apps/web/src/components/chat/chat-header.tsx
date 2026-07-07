"use client";

import { useChatStore } from "@/stores";
import { Bot, Circle } from "lucide-react";

export function ChatHeader() {
  const sessions = useChatStore((state) => state.sessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const currentSession = sessions.find(
    (session) => session.id === currentSessionId,
  );

  return (
    <div className="flex h-14 items-center justify-between border-b border-[#ededeb] px-5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-lg border bg-white">
          <Bot className="size-4" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">
            {currentSession?.title ?? "New conversation"}
          </h1>
          <p className="text-xs text-muted-foreground">
            sensenova / {currentSession?.type ?? "chat"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1.5 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground">
        <Circle className="size-2 fill-emerald-500 text-emerald-500" />
        Ready
      </div>
    </div>
  );
}

