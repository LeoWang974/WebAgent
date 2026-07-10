"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

interface AgentFeedbackMessageProps {
  detail: string;
  modelName: string;
  startedAt: string;
  stage: string;
}

function formatElapsed(startedAt: string, now: number) {
  const startedAtMs = new Date(startedAt).getTime();
  if (Number.isNaN(startedAtMs)) {
    return "计算中";
  }

  const totalSeconds = Math.max(0, Math.floor((now - startedAtMs) / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
}

export function AgentFeedbackMessage({
  detail,
  modelName,
  startedAt,
  stage,
}: AgentFeedbackMessageProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <article className="flex w-full justify-start gap-3">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-[#242424] text-[11px] font-medium text-white">
        A
      </div>
      <div className="max-w-[78%] rounded-2xl rounded-tl-md border bg-white px-4 py-3 text-sm leading-6 shadow-sm">
        <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          {modelName}
          <span className="normal-case">已等待 {formatElapsed(startedAt, now)}</span>
        </div>
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="size-1.5 rounded-full bg-emerald-500" />
          {stage}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
      </div>
    </article>
  );
}
