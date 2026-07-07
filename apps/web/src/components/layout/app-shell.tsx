import { ChatWorkspace } from "../chat";
import { MainLayout } from "./main-layout";

export function AppShell() {
  return (
    <MainLayout>
      <ChatWorkspace />
    </MainLayout>
  );
}
