"use client";

import { ArtifactPreviewContent } from "./artifact-preview-content";
import { ArtifactGroupedList } from "./artifact-grouped-list";
import { downloadArtifact } from "@/lib/artifact-actions";
import { useChatStore, useUiStore } from "@/stores";
import { Check, Download, Maximize2, MoreHorizontal, Trash2 } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";

interface ArtifactPanelProps {
  dragging?: boolean;
  width: number;
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

export function ArtifactPanel({ dragging = false, width }: ArtifactPanelProps) {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const artifacts = useChatStore((state) => state.artifacts);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const selectedArtifactId = useChatStore((state) => state.selectedArtifactId);
  const selectArtifact = useChatStore((state) => state.selectArtifact);
  const deleteArtifact = useChatStore((state) => state.deleteArtifact);
  const panelOpen = useUiStore((state) => state.artifactPanelOpen);
  const openFullscreen = useUiStore((state) => state.openArtifactFullscreen);
  const artifact = artifacts.find((item) => item.id === selectedArtifactId);
  const sessionArtifacts = artifacts.filter((item) => item.sessionId === currentSessionId);

  if (!panelOpen) {
    return null;
  }

  return (
    <aside
      className={`hidden shrink-0 border-l border-[#deded8] bg-[#f7f7f5] xl:flex xl:flex-col ${
        dragging ? "select-none" : ""
      }`}
      style={{ width }}
    >
      <div className="flex h-14 items-center justify-between border-b border-[#deded8] px-4">
        <div className="min-w-0">
          <div className="text-sm font-semibold">{t("artifact")}</div>
          {artifact ? (
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {artifact.title}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <button
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            disabled={!artifact}
            onClick={() => {
              if (artifact) {
                void downloadArtifact(artifact);
              }
            }}
            title={t("download")}
            type="button"
          >
            <Download className="size-4" />
          </button>
          <button
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            disabled={!artifact}
            onClick={openFullscreen}
            title={t("preview")}
            type="button"
          >
            <Maximize2 className="size-4" />
          </button>
          <div className="relative">
            <button
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground disabled:opacity-40"
              disabled={!artifact}
              onClick={() => setMenuOpen((value) => !value)}
              type="button"
            >
              <MoreHorizontal className="size-4" />
            </button>
            {menuOpen && artifact ? (
              <div className="absolute right-0 top-9 z-10 w-40 overflow-hidden rounded-lg border bg-white py-1 text-sm shadow-lg">
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted"
                  onClick={async () => {
                    try {
                      await copyText(artifact.title);
                      setCopied(true);
                      window.setTimeout(() => setCopied(false), 1200);
                    } catch {
                      setCopied(false);
                    }
                  }}
                  type="button"
                >
                  {copied ? <Check className="size-4" /> : null}
                  {copied ? t("copied") : t("copyTitle")}
                </button>
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 hover:bg-red-50"
                  onClick={() => {
                    deleteArtifact(artifact.id);
                    setMenuOpen(false);
                  }}
                  type="button"
                >
                  <Trash2 className="size-4" />
                  {t("deleteArtifact")}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <ArtifactGroupedList
          artifacts={sessionArtifacts}
          onSelect={selectArtifact}
          selectedArtifactId={selectedArtifactId}
        />
        <ArtifactPreviewContent artifact={artifact} />
      </div>
    </aside>
  );
}
