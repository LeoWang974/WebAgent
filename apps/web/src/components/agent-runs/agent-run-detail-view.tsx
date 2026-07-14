"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Boxes, Clock3, Loader2, TriangleAlert } from "lucide-react";
import { webAgentApi } from "@/services";
import type { AgentRun, AgentRunEvent } from "@/types";

interface AgentRunDetailViewProps {
  runId: string;
}

interface RunArtifactSummary {
  id: string;
  title: string;
  type: string;
}

const terminalStatuses: AgentRun["status"][] = [
  "completed",
  "failed",
  "cancelled",
  "disconnected",
];

function isTerminalStatus(status: AgentRun["status"]) {
  return terminalStatuses.includes(status);
}

function formatDuration(startedAt?: string, completedAt?: string) {
  if (!startedAt) {
    return "-";
  }
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

function getArtifactSummary(event: AgentRunEvent): RunArtifactSummary | undefined {
  if (event.eventType !== "artifact_created" || !event.payload) {
    return undefined;
  }
  const id = event.payload.artifactId;
  const type = event.payload.artifactType;
  const title = event.payload.title;
  if (typeof id !== "string") {
    return undefined;
  }
  return {
    id,
    title: typeof title === "string" ? title : id,
    type: typeof type === "string" ? type : "artifact",
  };
}

export function AgentRunDetailView({ runId }: AgentRunDetailViewProps) {
  const [run, setRun] = useState<AgentRun>();
  const [events, setEvents] = useState<AgentRunEvent[]>([]);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    let unsubscribe: (() => void) | undefined;

    async function loadRun() {
      try {
        const loadedRun = await webAgentApi.getAgentRun(runId);
        if (!mounted) {
          return;
        }
        setRun(loadedRun);
        setEvents(
          loadedRun.steps.map((step) => ({
            eventType: "step",
            progress: loadedRun.progress,
            runId: loadedRun.id,
            status: loadedRun.status,
            step,
          })),
        );
        unsubscribe = webAgentApi.subscribeAgentRun(runId, (event) => {
          setRun((currentRun) =>
            currentRun
              ? {
                  ...currentRun,
                  completedAt: event.completedAt ?? currentRun.completedAt,
                  error: event.error ?? currentRun.error,
                  output: event.output ?? currentRun.output,
                  progress: event.progress,
                  status: event.status,
                }
              : currentRun,
          );
          setEvents((currentEvents) =>
            currentEvents.some((item) => item.step.id === event.step.id)
              ? currentEvents.map((item) =>
                  item.step.id === event.step.id ? event : item,
                )
              : [...currentEvents, event],
          );
          if (isTerminalStatus(event.status)) {
            unsubscribe?.();
            unsubscribe = undefined;
          }
        });
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "加载 Run 详情失败。");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    void loadRun();

    return () => {
      mounted = false;
      unsubscribe?.();
    };
  }, [runId]);

  const artifacts = useMemo(() => {
    const summaries = events
      .map(getArtifactSummary)
      .filter((artifact): artifact is RunArtifactSummary => Boolean(artifact));
    return Array.from(new Map(summaries.map((artifact) => [artifact.id, artifact])).values());
  }, [events]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" />
        正在加载 Run 详情...
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <Link className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground" href="/app">
          <ArrowLeft className="size-4" />
          返回工作区
        </Link>
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error ?? "Run 不存在。"}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-5xl space-y-5 p-6">
        <Link className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground" href={`/app/chat/${run.sessionId}`}>
          <ArrowLeft className="size-4" />
          返回会话
        </Link>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-lg font-semibold">{run.title}</h1>
              <p className="mt-1 text-xs text-muted-foreground">{run.id}</p>
            </div>
            <span className="rounded-full border bg-[#f7f7f5] px-3 py-1 text-xs">
              {run.status} / {run.progress}%
            </span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-[#242424]" style={{ width: `${run.progress}%` }} />
          </div>
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-lg border bg-[#fbfbfa] p-3">
              <div className="text-xs text-muted-foreground">适配器</div>
              <div className="mt-1 font-medium">{run.adapterKey ?? "-"}</div>
            </div>
            <div className="rounded-lg border bg-[#fbfbfa] p-3">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock3 className="size-3.5" />
                耗时
              </div>
              <div className="mt-1 font-medium">{formatDuration(run.startedAt, run.completedAt)}</div>
            </div>
            <div className="rounded-lg border bg-[#fbfbfa] p-3">
              <div className="text-xs text-muted-foreground">事件数</div>
              <div className="mt-1 font-medium">{events.length}</div>
            </div>
          </div>
          {run.error ? (
            <div className="mt-4 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <span>{run.error}</span>
            </div>
          ) : null}
        </section>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Boxes className="size-4" />
            产物
          </div>
          {artifacts.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {artifacts.map((artifact) => (
                <Link
                  className="rounded-lg border bg-[#fbfbfa] p-3 text-sm hover:border-[#c9c7c0]"
                  href={`/app/chat/${run.sessionId}`}
                  key={artifact.id}
                >
                  <div className="font-medium">{artifact.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {artifact.type} · {artifact.id}
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              暂无产物事件。
            </div>
          )}
        </section>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-semibold">事件时间线</div>
          <div className="space-y-3">
            {events.map((event, index) => (
              <div className="rounded-lg border bg-[#fbfbfa] p-3" key={event.step.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-medium text-muted-foreground">
                    #{index + 1} · {event.eventType} · {new Date(event.step.timestamp).toLocaleString()}
                  </div>
                  <span className="rounded-full border bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
                    {event.step.status}
                  </span>
                </div>
                <div className="mt-2 whitespace-pre-wrap text-sm leading-6">{event.step.label}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
