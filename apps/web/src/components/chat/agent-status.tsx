"use client";

import type { AgentRun } from "@/types";
import { useChatStore } from "@/stores";
import { useI18n } from "@/lib/i18n";
import { getStatusLabelKey } from "@/lib/status";
import {
  Check,
  CircleDashed,
  Loader2,
  Square,
  TriangleAlert,
} from "lucide-react";

export function AgentStatus() {
  const { t } = useI18n();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const agentRuns = useChatStore((state) => state.agentRuns);
  const run = agentRuns.find((item) => item.sessionId === currentSessionId);

  if (!run) {
    return null;
  }

  const active = !["completed", "failed", "cancelled"].includes(run.status);

  return (
    <div className="border-t border-[#ededeb] bg-[#fbfbfa] px-5 py-3">
      <div className="mx-auto max-w-3xl rounded-xl border bg-white p-3 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-[#f7f7f5]">
              {run.status === "failed" ? (
                <TriangleAlert className="size-4 text-red-500" />
              ) : active ? (
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              ) : (
                <Check className="size-4 text-emerald-600" />
              )}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{run.title}</div>
              <div className="text-xs text-muted-foreground">
                {t(getStatusLabelKey(run.status))} / {run.progress}%
              </div>
            </div>
          </div>
          <button
            className="flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
            disabled={!active}
            type="button"
          >
            <Square className="size-3" />
            {t("stop")}
          </button>
        </div>

        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-[#242424] transition-all duration-300"
            style={{ width: `${run.progress}%` }}
          />
        </div>

        <div className="mt-3 space-y-2">
          {run.steps.map((step) => (
            <div className="flex items-center gap-2 text-xs" key={step.id}>
              <span className="flex size-4 items-center justify-center rounded-full border bg-white">
                {step.status === "completed" ? (
                  <Check className="size-3 text-emerald-600" />
                ) : step.status === "failed" ? (
                  <TriangleAlert className="size-3 text-red-500" />
                ) : (
                  <CircleDashed className="size-3 text-muted-foreground" />
                )}
              </span>
              <span
                className={
                  step.status === "running"
                    ? "font-medium text-foreground"
                    : "text-muted-foreground"
                }
              >
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
