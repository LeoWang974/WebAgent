/**
 * File purpose: Renders and coordinates the main layout user-interface feature.
 * Main declarations: MainLayout handles main layout.
 */

import { MobileSidebarDrawer } from "./mobile-sidebar-drawer";
import type { ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { ThemeEffect } from "./theme-effect";
import { Topbar } from "./topbar";
import { WorkspaceHydrator } from "./workspace-hydrator";

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-[#f7f7f5] text-foreground">
      <WorkspaceHydrator />
      <ThemeEffect />
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <MobileSidebarDrawer />
      <main className="flex min-w-0 flex-1 flex-col bg-background">
        <Topbar />
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </main>
    </div>
  );
}
