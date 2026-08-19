/**
 * File purpose: Renders and coordinates the sidebar user-interface feature.
 * Main declarations: Sidebar handles sidebar.
 */

"use client";

import { NewChatButton } from "../sidebar/new-chat-button";
import { SessionList } from "../sidebar/session-list";
import { SessionSearch } from "../sidebar/session-search";
import { UserMenu } from "../sidebar/user-menu";
import { Settings, Shield } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { useUiStore, useUserStore } from "@/stores";

interface SidebarProps {
  variant?: "default" | "drawer";
}

export function Sidebar({ variant = "default" }: SidebarProps) {
  const { t } = useI18n();
  const closeSidebarDrawer = useUiStore((state) => state.closeSidebarDrawer);
  const user = useUserStore((state) => state.user);

  return (
    <aside className="flex h-screen w-full shrink-0 flex-col border-r border-[#deded8] bg-[#f4f4ef] md:w-[264px]">
      <div className="space-y-3 border-b border-[#deded8] p-2.5">
        <div className="flex items-center gap-2 px-1.5">
          <div className="flex size-7 items-center justify-center rounded-md bg-[#242424] text-xs font-semibold text-white">
            W
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">WebAgent</div>
            <div className="text-[11px] text-muted-foreground">
              {t("agentWorkspace")}
            </div>
          </div>
        </div>
        <NewChatButton />
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-2.5">
        <SessionSearch />
        <SessionList />
      </div>
      <div className="space-y-1 border-t border-[#deded8] p-2.5">
        {user?.role === "admin" ? (
          <Link
            className="flex h-8 items-center gap-2 rounded-md px-2 text-sm text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
            href="/app/admin"
            onClick={() => {
              if (variant === "drawer") {
                closeSidebarDrawer();
              }
            }}
          >
            <Shield className="size-4" />
            <span>{t("admin")}</span>
          </Link>
        ) : null}
        <Link
          className="flex h-8 items-center gap-2 rounded-md px-2 text-sm text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
          href="/app/settings"
          onClick={() => {
            if (variant === "drawer") {
              closeSidebarDrawer();
            }
          }}
        >
          <Settings className="size-4" />
          <span>{t("settings")}</span>
        </Link>
        <UserMenu />
      </div>
    </aside>
  );
}
