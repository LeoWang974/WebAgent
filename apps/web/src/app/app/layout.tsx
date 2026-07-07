import { MainLayout } from "@/components/layout";
import type { ReactNode } from "react";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return <MainLayout>{children}</MainLayout>;
}

