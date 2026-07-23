"use client";

import { useMemo, useState } from "react";
import { FileJson, FileText, Image, Presentation, Table2 } from "lucide-react";
import type { Artifact, ArtifactType } from "@/types";
import { compareArtifactsForPreview } from "@/lib/artifact-selection";

interface ArtifactGroupedListProps {
  artifacts: Artifact[];
  selectedArtifactId?: string;
  onSelect: (artifactId: string) => void;
}

type GroupMode = "run" | "type" | "time";

const typeLabel: Record<ArtifactType, string> = {
  chart: "图表",
  data_table: "表格",
  debug_json: "JSON",
  html_page: "HTML",
  image_result: "图片",
  markdown_report: "Markdown",
  ppt_deck: "PPT",
};

const typeIcon: Record<ArtifactType, typeof FileText> = {
  chart: Table2,
  data_table: Table2,
  debug_json: FileJson,
  html_page: FileText,
  image_result: Image,
  markdown_report: FileText,
  ppt_deck: Presentation,
};

function artifactTime(artifact: Artifact) {
  const value =
    artifact.createdAt ??
    (typeof artifact.metadata?.updatedAt === "string" ? artifact.metadata.updatedAt : undefined);
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function timeGroupLabel(artifact: Artifact) {
  const timestamp = artifactTime(artifact);
  if (!timestamp) {
    return "时间未知";
  }
  return new Date(timestamp).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

function runGroupLabel(artifact: Artifact) {
  return artifact.runId ? `Run ${artifact.runId.slice(0, 8)}` : "未关联 Run";
}

function buildGroups(artifacts: Artifact[], mode: GroupMode) {
  const groups = new Map<string, Artifact[]>();
  const sortedArtifacts = [...artifacts].sort(compareArtifactsForPreview);

  for (const artifact of sortedArtifacts) {
    const key =
      mode === "run"
        ? runGroupLabel(artifact)
        : mode === "type"
          ? typeLabel[artifact.type]
          : timeGroupLabel(artifact);
    groups.set(key, [...(groups.get(key) ?? []), artifact]);
  }

  return Array.from(groups.entries()).map(([label, items]) => ({ items, label }));
}

export function ArtifactGroupedList({
  artifacts,
  onSelect,
  selectedArtifactId,
}: ArtifactGroupedListProps) {
  const [mode, setMode] = useState<GroupMode>("run");
  const groups = useMemo(() => buildGroups(artifacts, mode), [artifacts, mode]);

  if (!artifacts.length) {
    return null;
  }

  return (
    <div className="mb-3 rounded-lg border bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="text-xs font-semibold text-muted-foreground">产物列表</div>
        <div className="flex rounded-md border bg-[#f7f7f5] p-0.5">
          {[
            ["run", "Run"],
            ["type", "类型"],
            ["time", "时间"],
          ].map(([value, label]) => (
            <button
              className={`rounded px-2 py-1 text-[11px] ${
                mode === value
                  ? "bg-white text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              key={value}
              onClick={() => setMode(value as GroupMode)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="max-h-56 overflow-y-auto p-2">
        {groups.map((group) => (
          <div className="mb-2 last:mb-0" key={group.label}>
            <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map((artifact) => {
                const Icon = typeIcon[artifact.type];
                return (
                  <button
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[#f2f2ef] ${
                      artifact.id === selectedArtifactId ? "bg-[#f2f2ef] ring-1 ring-[#deded8]" : ""
                    }`}
                    key={artifact.id}
                    onClick={() => onSelect(artifact.id)}
                    type="button"
                  >
                    <Icon className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate text-xs">{artifact.title}</span>
                    <span className="shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {typeLabel[artifact.type]}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
