"use client";

import { ArtifactPreviewContent } from "./artifact-preview-content";
import { useChatStore } from "@/stores";
import { Download, Maximize2, MoreHorizontal } from "lucide-react";

export function ArtifactPanel() {
  const artifacts = useChatStore((state) => state.artifacts);
  const selectedArtifactId = useChatStore((state) => state.selectedArtifactId);
  const artifact = artifacts.find((item) => item.id === selectedArtifactId);

  return (
    <aside className="hidden w-[420px] shrink-0 border-l border-[#deded8] bg-[#f7f7f5] xl:flex xl:flex-col">
      <div className="flex h-14 items-center justify-between border-b border-[#deded8] px-4">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Artifact</div>
          {artifact ? (
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {artifact.title}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <button
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            type="button"
          >
            <Download className="size-4" />
          </button>
          <button
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            type="button"
          >
            <Maximize2 className="size-4" />
          </button>
          <button
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            type="button"
          >
            <MoreHorizontal className="size-4" />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <ArtifactPreviewContent artifact={artifact} />
      </div>
    </aside>
  );
}
