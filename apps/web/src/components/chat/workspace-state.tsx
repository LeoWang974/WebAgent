/**
 * File purpose: Renders and coordinates the workspace state user-interface feature.
 * Main declarations: WorkspaceState handles workspace state.
 */

"use client";

import { useChatStore } from "@/stores";
import { Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function WorkspaceState() {
  const { t } = useI18n();
  const error = useChatStore((state) => state.error);
  const hydrated = useChatStore((state) => state.hydrated);
  const loading = useChatStore((state) => state.loading);
  const retryHydrate = useChatStore((state) => state.retryHydrate);

  if (loading && !hydrated) {
    return (
      <div className="absolute inset-x-0 top-0 z-20 border-b bg-white/90 px-4 py-2 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          {t("loadingWorkspace")}
        </div>
      </div>
    );
  }

  if (!error) {
    return null;
  }

  return (
    <div className="absolute inset-x-0 top-0 z-20 border-b border-red-100 bg-red-50 px-4 py-2">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 text-xs text-red-700">
        <div className="flex min-w-0 items-center gap-2">
          <TriangleAlert className="size-3.5 shrink-0" />
          <span className="truncate">
            {t("workspaceLoadFailed")}: {error}
          </span>
        </div>
        <button
          className="flex shrink-0 items-center gap-1 rounded-md border border-red-200 bg-white px-2 py-1 hover:bg-red-50"
          onClick={() => void retryHydrate()}
          type="button"
        >
          <RotateCcw className="size-3" />
          {t("retry")}
        </button>
      </div>
    </div>
  );
}
