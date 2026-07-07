"use client";

import { ArtifactCard } from "../artifacts";
import { AssistantMessage } from "./assistant-message";
import { EmptyConversation } from "./empty-conversation";
import { UserMessage } from "./user-message";
import { useChatStore, useUiStore } from "@/stores";

export function MessageList() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const allMessages = useChatStore((state) => state.messages);
  const artifacts = useChatStore((state) => state.artifacts);
  const selectArtifact = useChatStore((state) => state.selectArtifact);
  const openArtifactDrawer = useUiStore((state) => state.openArtifactDrawer);
  const messages = allMessages.filter(
    (message) => message.sessionId === currentSessionId,
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-6">
        {messages.length === 0 ? (
          <EmptyConversation />
        ) : null}
        {messages.map((message) => {
          const messageArtifacts = artifacts.filter((artifact) =>
            message.artifactIds?.includes(artifact.id),
          );

          return (
            <div className="space-y-2" key={message.id}>
              {message.role === "user" ? (
                <UserMessage content={message.content} />
              ) : (
                <AssistantMessage content={message.content} />
              )}
              {messageArtifacts.map((artifact) => (
                <ArtifactCard
                  key={artifact.id}
                  onClick={() => {
                    selectArtifact(artifact.id);
                    openArtifactDrawer();
                  }}
                  status={artifact.status}
                  title={artifact.title}
                  type={artifact.type}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
