/**
 * File purpose: Renders and coordinates the artifact grouped list user-interface feature.
 * Main declarations: artifactTime handles artifact time; timeGroupLabel handles time group label;
 * runGroupLabel handles run group label; buildGroups handles build groups; ArtifactGroupedList
 * handles artifact grouped list.
 */

"use client";

import { useMemo, useState } from "react";
import { FileJson, FileText, Image, Presentation, Table2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import type { Artifact, ArtifactType } from "@/types";
import { compareArtifactsForPreview } from "@/lib/artifact-selection";

interface ArtifactGroupedListProps {
  artifacts: Artifact[];
  selectedArtifactId?: string;
  onSelect: (artifactId: string) => void;
}

type GroupMode = "run" | "type" | "time";

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

function timeGroupLabel(artifact: Artifact, unknownLabel: string) {
  const timestamp = artifactTime(artifact);
  if (!timestamp) {
    return unknownLabel;
  }
  return new Date(timestamp).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

function runGroupLabel(artifact: Artifact, unlinkedLabel: string) {
  return artifact.runId ? `Run ${artifact.runId.slice(0, 8)}` : unlinkedLabel;
}

function buildGroups(
  artifacts: Artifact[],
  mode: GroupMode,
  typeLabels: Record<ArtifactType, string>,
  unknownTimeLabel: string,
  unlinkedRunLabel: string,
) {
  const groups = new Map<string, Artifact[]>();
  const sortedArtifacts = [...artifacts].sort(compareArtifactsForPreview);

  for (const artifact of sortedArtifacts) {
    const key =
      mode === "run"
        ? runGroupLabel(artifact, unlinkedRunLabel)
        : mode === "type"
          ? typeLabels[artifact.type]
          : timeGroupLabel(artifact, unknownTimeLabel);
    const existingGroup = groups.get(key);
    if (existingGroup) {
      existingGroup.push(artifact);
    } else {
      groups.set(key, [artifact]);
    }
  }

  return Array.from(groups.entries()).map(([label, items]) => ({ items, label }));
}

export function ArtifactGroupedList({
  artifacts,
  onSelect,
  selectedArtifactId,
}: ArtifactGroupedListProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<GroupMode>("run");
  const typeLabels = useMemo<Record<ArtifactType, string>>(
    () => ({
      chart: t("artifactTypeChart"),
      data_table: t("artifactTypeTable"),
      debug_json: "JSON",
      html_page: "HTML",
      image_result: t("artifactTypeImage"),
      markdown_report: "Markdown",
      ppt_deck: "PPT",
    }),
    [t],
  );
  const groups = useMemo(
    () =>
      buildGroups(
        artifacts,
        mode,
        typeLabels,
        t("artifactTimeUnknown"),
        t("artifactUnlinkedRun"),
      ),
    [artifacts, mode, t, typeLabels],
  );

  if (!artifacts.length) {
    return null;
  }

  return (
    <div className="mb-3 rounded-lg border bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="text-xs font-semibold text-muted-foreground">{t("artifactList")}</div>
        <div className="flex rounded-md border bg-[#f7f7f5] p-0.5">
          {[
            ["run", t("artifactGroupRun")],
            ["type", t("artifactGroupType")],
            ["time", t("artifactGroupTime")],
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
                      {typeLabels[artifact.type]}
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
