"use client";

import { Menu, PanelRight, RefreshCw, Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useChatStore, useUiStore } from "@/stores";

function formatCheckedAt(value?: string) {
  if (!value) {
    return "尚未检查";
  }
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Topbar() {
  const { t } = useI18n();
  const openSidebarDrawer = useUiStore((state) => state.openSidebarDrawer);
  const toggleArtifactPanel = useUiStore((state) => state.toggleArtifactPanel);
  const models = useChatStore((state) => state.models);
  const selectedModelId = useChatStore((state) => state.selectedModelId);
  const refreshRuntimeModelStatus = useChatStore((state) => state.refreshRuntimeModelStatus);
  const runtimeStatusCheckedAt = useChatStore((state) => state.runtimeStatusCheckedAt);
  const runtimeStatusRefreshing = useChatStore((state) => state.runtimeStatusRefreshing);
  const selectedModel = models.find((model) => model.id === selectedModelId);
  const runtimeConnected = selectedModel?.isAvailable !== false;

  function focusSessionSearch() {
    const shouldOpenDrawer = window.matchMedia("(max-width: 767px)").matches;
    if (shouldOpenDrawer) {
      openSidebarDrawer();
    }
    window.setTimeout(() => {
      const inputs = Array.from(
        document.querySelectorAll<HTMLInputElement>("[data-session-search-input]"),
      );
      (inputs.find((input) => input.offsetParent !== null) ?? inputs[0])?.focus();
    }, shouldOpenDrawer ? 60 : 0);
  }

  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-[#e5e5df] bg-background px-4">
      <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <button
          aria-label={t("openSidebar")}
          className="-ml-1 flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
          onClick={openSidebarDrawer}
          type="button"
        >
          <Menu className="size-4" />
        </button>
        <span>{t("workspace")}</span>
        <span className="rounded-full border px-2 py-0.5 text-[11px] font-normal text-muted-foreground">
          {t("preview")}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <div
          className="hidden items-center gap-1.5 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground md:flex"
          title={`${selectedModel?.baseUrl ?? "未配置地址"} / ${
            selectedModel?.runtimeStatus?.message ?? "Hermes 运行时"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${
              runtimeConnected ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
          <span>Hermes</span>
          <span>{runtimeConnected ? "已连接" : "未连接"}</span>
          <span className="text-muted-foreground/70">
            {formatCheckedAt(runtimeStatusCheckedAt)}
          </span>
          <button
            className="ml-0.5 flex size-5 items-center justify-center rounded-full hover:bg-muted disabled:opacity-50"
            disabled={runtimeStatusRefreshing}
            onClick={() => void refreshRuntimeModelStatus()}
            title="刷新 Hermes 状态"
            type="button"
          >
            <RefreshCw
              className={`size-3 ${runtimeStatusRefreshing ? "animate-spin" : ""}`}
            />
          </button>
        </div>
        <button
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={focusSessionSearch}
          title={t("search")}
          type="button"
        >
          <Search className="size-4" />
        </button>
        <button
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={toggleArtifactPanel}
          title={t("toggleArtifactPanel")}
          type="button"
        >
          <PanelRight className="size-4" />
        </button>
      </div>
    </header>
  );
}
