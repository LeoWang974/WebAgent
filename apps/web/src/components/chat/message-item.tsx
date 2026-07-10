"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MessageItemProps {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  createdAt: string;
  isPending?: boolean;
  pendingLabel?: string;
  waitDurationMs?: number;
  waitStartedAt?: string;
}

function formatTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatDuration(durationMs?: number) {
  if (
    durationMs === undefined ||
    !Number.isFinite(durationMs) ||
    durationMs < 1000
  ) {
    return "0 秒";
  }

  const totalSeconds = Math.round(durationMs / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
}

function useElapsed(startedAt?: string) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [startedAt]);

  if (!startedAt) {
    return undefined;
  }

  const startedAtMs = new Date(startedAt).getTime();
  if (Number.isNaN(startedAtMs)) {
    return undefined;
  }

  return Math.max(0, now - startedAtMs);
}

export function MessageItem({
  role,
  content,
  createdAt,
  isPending,
  pendingLabel,
  waitDurationMs,
  waitStartedAt,
}: MessageItemProps) {
  const isUser = role === "user";
  const messageTime = formatTime(createdAt);
  const pendingElapsedMs = useElapsed(isPending ? waitStartedAt ?? createdAt : undefined);
  const waitDuration = isPending
    ? formatDuration(pendingElapsedMs)
    : waitDurationMs
      ? formatDuration(waitDurationMs)
      : undefined;

  return (
    <article
      className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser ? (
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-[#242424] text-[11px] font-medium text-white">
          A
        </div>
      ) : null}
      <div
        className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
          isUser
            ? "rounded-tr-md bg-[#242424] text-white"
            : "rounded-tl-md border bg-white"
        }`}
      >
        <div
          className={`mb-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] font-medium ${
            isUser ? "text-white/60" : "text-muted-foreground"
          }`}
        >
          <span className="uppercase">{role}</span>
          {messageTime ? <span>{messageTime}</span> : null}
          {!isUser && waitDuration ? (
            <span>{isPending ? `已等待 ${waitDuration}` : `等待 ${waitDuration}`}</span>
          ) : null}
        </div>
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : isPending ? (
          <div className="flex items-start gap-2 text-muted-foreground">
            <Loader2 className="mt-1 size-3.5 shrink-0 animate-spin" />
            <span>{pendingLabel ?? "Hermes 正在工作，等待阶段反馈..."}</span>
          </div>
        ) : (
          <div className="message-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      {isUser ? (
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border bg-white text-[11px] font-medium">
          U
        </div>
      ) : null}
    </article>
  );
}
