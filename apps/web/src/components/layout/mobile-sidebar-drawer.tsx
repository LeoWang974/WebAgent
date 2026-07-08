"use client";

import { Sidebar } from "./sidebar";
import { useUiStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

export function MobileSidebarDrawer() {
  const { t } = useI18n();
  const open = useUiStore((state) => state.sidebarDrawerOpen);
  const close = useUiStore((state) => state.closeSidebarDrawer);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <button
        aria-label={t("closeSidebar")}
        className="absolute inset-y-0 right-0 bg-black/30"
        onClick={close}
        style={{ left: "min(280px, 86vw)" }}
        type="button"
      />
      <div className="absolute inset-y-0 left-0 w-[280px] max-w-[86vw] shadow-2xl">
        <Sidebar variant="drawer" />
      </div>
    </div>
  );
}
