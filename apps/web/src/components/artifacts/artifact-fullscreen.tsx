"use client";

import { ArtifactPreviewContent } from "./artifact-preview-content";
import { downloadArtifact } from "@/lib/artifact-actions";
import { useChatStore, useUiStore } from "@/stores";
import { Download, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useEffect } from "react";

export function ArtifactFullscreen() {
  const { t } = useI18n();
  const artifacts = useChatStore((state) => state.artifacts);
  const selectedArtifactId = useChatStore((state) => state.selectedArtifactId);
  const ensureArtifactLoaded = useChatStore((state) => state.ensureArtifactLoaded);
  const open = useUiStore((state) => state.artifactFullscreenOpen);
  const close = useUiStore((state) => state.closeArtifactFullscreen);
  const artifact = artifacts.find((item) => item.id === selectedArtifactId);

  useEffect(() => {
    if (open && selectedArtifactId) {
      void ensureArtifactLoaded(selectedArtifactId);
    }
  }, [ensureArtifactLoaded, open, selectedArtifactId]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-[#f7f7f5]">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#deded8] bg-white px-4">
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
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
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
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            onClick={close}
            title={t("close")}
            type="button"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto max-w-6xl">
          <ArtifactPreviewContent artifact={artifact} />
        </div>
      </div>
    </div>
  );
}
