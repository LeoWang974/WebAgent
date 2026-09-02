/**
 * File purpose: Renders and coordinates the agent status user-interface feature.
 * Main declarations: AgentStatus handles agent status.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Check,
  ClipboardList,
  Loader2,
  TriangleAlert,
  X,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { getStatusLabelKey } from "@/lib/status";
import { useChatStore } from "@/stores";
import { isAgentRunActive, selectAgentStatusRun } from "./agent-status-model";

export function AgentStatus() {
  const { t } = useI18n();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const agentRuns = useChatStore((state) => state.agentRuns);
  const refreshAgentRun = useChatStore((state) => state.refreshAgentRun);
  const run = selectAgentStatusRun(agentRuns, currentSessionId);
  const active = isAgentRunActive(run);
  const compactPlainChat = Boolean(run?.isPlainChat && run.hasAssistantResponse && active);

  async function openDetails() {
    if (!run) {
      return;
    }

    setDetailsOpen(true);
    if (active) {
      setLoadingDetails(false);
      return;
    }
    setLoadingDetails(true);
    await refreshAgentRun(run.id);
    setLoadingDetails(false);
  }

  if (!run) {
    return null;
  }

  if (compactPlainChat) {
    return (
      <div className="border-t border-[#ededeb] bg-[#fbfbfa] px-5 py-2">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 rounded-lg border bg-white px-3 py-2 text-xs text-muted-foreground shadow-sm">
          <div className="flex min-w-0 items-center gap-2">
            <Loader2 className="size-3.5 shrink-0 animate-spin" />
            <span className="truncate">{t("agentRunPlainChatConfirming")}</span>
          </div>
          <Link
            className="shrink-0 rounded-md border px-2 py-1 hover:bg-muted hover:text-foreground"
            href={`/app/runs/${run.id}`}
          >
            {t("agentRunShowDetails")}
          </Link>
        </div>
      </div>
    );
  }

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
          <div className="flex shrink-0 items-center gap-2">
            <Link
              className="flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              href={`/app/runs/${run.id}`}
            >
              <ClipboardList className="size-3.5" />
              {t("agentRunDetailsPage")}
            </Link>
            <button
              className="flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={openDetails}
              type="button"
            >
              <ClipboardList className="size-3.5" />
              {t("agentRunShowDetails")}
            </button>
          </div>
        </div>

        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-[#242424] transition-all duration-300"
            style={{ width: `${run.progress}%` }}
          />
        </div>
      </div>

      {detailsOpen ? (
        <div className="fixed inset-0 z-50 flex items-end bg-black/20 sm:items-center sm:justify-center">
          <div className="max-h-[82vh] w-full overflow-hidden rounded-t-2xl border bg-white shadow-xl sm:max-w-2xl sm:rounded-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <div className="text-sm font-semibold">{t("agentRunDetails")}</div>
                <div className="text-xs text-muted-foreground">
                  {run.id} · {t(getStatusLabelKey(run.status))} · {run.progress}%
                </div>
              </div>
              <button
                aria-label={t("close")}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setDetailsOpen(false)}
                type="button"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="max-h-[68vh] overflow-y-auto p-4">
              {loadingDetails ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {t("agentRunLoadingEvents")}
                </div>
              ) : null}
              <div className="space-y-3">
                {Array.from(new Map(run.steps.map((step) => [step.id, step])).values()).map((step, index) => (
                  <div className="rounded-lg border bg-[#fbfbfa] p-3" key={step.id}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-medium text-muted-foreground">
                        #{index + 1} · {new Date(step.timestamp).toLocaleTimeString()}
                      </div>
                      <span className="rounded-full border bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
                        {step.status}
                      </span>
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground">
                      {step.label}
                    </div>
                  </div>
                ))}
                {run.steps.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                    {t("agentRunEventsEmpty")}
                  </div>
                ) : null}
              </div>
              {run.error ? (
                <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {run.error}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
