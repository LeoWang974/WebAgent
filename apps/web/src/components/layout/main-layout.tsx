import { ArtifactPanel } from "../artifacts";
import { ChatHeader, MessageList } from "../chat";
import { ChatComposer } from "../composer";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function MainLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-[#f7f7f5] text-foreground">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col bg-background">
        <Topbar />
        <div className="flex min-h-0 flex-1">
          <section className="flex min-w-0 flex-1 flex-col">
            <ChatHeader />
            <div className="min-h-0 flex-1 overflow-hidden">
              <MessageList />
            </div>
            <ChatComposer />
          </section>
          <ArtifactPanel />
        </div>
      </main>
    </div>
  );
}
