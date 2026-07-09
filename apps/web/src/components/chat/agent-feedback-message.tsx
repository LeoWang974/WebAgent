"use client";

import { Loader2 } from "lucide-react";

interface AgentFeedbackMessageProps {
  detail: string;
  modelName: string;
  stage: string;
}

export function AgentFeedbackMessage({
  detail,
  modelName,
  stage,
}: AgentFeedbackMessageProps) {
  return (
    <article className="flex w-full justify-start gap-3">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-[#242424] text-[11px] font-medium text-white">
        A
      </div>
      <div className="max-w-[78%] rounded-2xl rounded-tl-md border bg-white px-4 py-3 text-sm leading-6 shadow-sm">
        <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          {modelName}
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
