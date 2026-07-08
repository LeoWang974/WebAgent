"use client";

import { Menu, PanelRight, Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useUiStore } from "@/stores";

export function Topbar() {
  const { t } = useI18n();
  const openSidebarDrawer = useUiStore((state) => state.openSidebarDrawer);
  const toggleArtifactPanel = useUiStore((state) => state.toggleArtifactPanel);

  function focusSessionSearch() {
    const shouldOpenDrawer = window.matchMedia("(max-width: 767px)").matches;

    if (shouldOpenDrawer) {
      openSidebarDrawer();
    }

    window.setTimeout(() => {
      const inputs = Array.from(
        document.querySelectorAll<HTMLInputElement>("[data-session-search-input]"),
      );
      const visibleInput =
        inputs.find((input) => input.offsetParent !== null) ?? inputs[0];

      visibleInput?.focus();
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
