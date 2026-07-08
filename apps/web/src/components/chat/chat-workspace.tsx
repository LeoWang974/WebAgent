import { ArtifactDrawer, ArtifactPanel } from "../artifacts";
import { ChatComposer } from "../composer";
import { AgentStatus } from "./agent-status";
import { ChatHeader } from "./chat-header";
import { MessageList } from "./message-list";
import { RouteSessionSync } from "./route-session-sync";

interface ChatWorkspaceProps {
  sessionId?: string;
}

export function ChatWorkspace({ sessionId }: ChatWorkspaceProps) {
  return (
    <div className="flex h-full min-h-0">
      <RouteSessionSync sessionId={sessionId} />
      <section className="flex min-w-0 flex-1 flex-col">
        <ChatHeader />
        <div className="min-h-0 flex-1 overflow-hidden">
          <MessageList />
        </div>
        <AgentStatus />
        <ChatComposer />
      </section>
      <ArtifactPanel />
      <ArtifactDrawer />
    </div>
  );
}
