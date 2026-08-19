/**
 * File purpose: Defines the Next.js layout route or route layout.
 * Main declarations: WorkspaceLayout handles workspace layout.
 */

import { MainLayout } from "@/components/layout";
import type { ReactNode } from "react";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return <MainLayout>{children}</MainLayout>;
}

