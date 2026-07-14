"use client";

import { ArtifactPreviewContent } from "./artifact-preview-content";
import { downloadArtifact } from "@/lib/artifact-actions";
import { useChatStore, useUiStore } from "@/stores";
import { Download, Maximize2, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function ArtifactDrawer() {
  const { t } = useI18n();
  const artifacts = useChatStore((state) => state.artifacts);
  const selectedArtifactId = useChatStore((state) => state.selectedArtifactId);
  const open = useUiStore((state) => state.artifactDrawerOpen);
  const close = useUiStore((state) => state.closeArtifactDrawer);
  const openFullscreen = useUiStore((state) => state.openArtifactFullscreen);
  const artifact = artifacts.find((item) => item.id === selectedArtifactId);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 xl:hidden">
      <button
        aria-label={t("closeArtifactPreview")}
        className="absolute inset-0 bg-black/30"
        onClick={close}
        type="button"
      />
      <aside className="absolute inset-x-0 bottom-0 flex max-h-[86vh] min-h-[60vh] flex-col rounded-t-2xl border bg-[#f7f7f5] shadow-2xl">
        <div className="flex h-14 items-center justify-between border-b px-4">
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
            <button
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
              onClick={close}
              type="button"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <ArtifactPreviewContent artifact={artifact} />
        </div>
      </aside>
    </div>
  );
}
