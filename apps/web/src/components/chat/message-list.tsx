"use client";

import { ArtifactCard } from "../artifacts";
import { AssistantMessage } from "./assistant-message";
import { EmptyConversation } from "./empty-conversation";
import { UserMessage } from "./user-message";
import { useChatStore, useUiStore } from "@/stores";
import { ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";

export function MessageList() {
  const { t } = useI18n();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const allMessages = useChatStore((state) => state.messages);
  const artifacts = useChatStore((state) => state.artifacts);
  const agentRuns = useChatStore((state) => state.agentRuns);
  const activeAgentRunId = useChatStore((state) => state.activeAgentRunId);
  const selectArtifact = useChatStore((state) => state.selectArtifact);
  const openArtifactDrawer = useUiStore((state) => state.openArtifactDrawer);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [nearBottom, setNearBottom] = useState(true);
  const messages = allMessages.filter(
    (message) => message.sessionId === currentSessionId,
  );
  const currentRun = agentRuns.find((run) => run.sessionId === currentSessionId);
  const lastMessageId = messages.at(-1)?.id;

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    window.requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior, block: "end" });
    });
  }

  useEffect(() => {
    scrollToBottom("auto");
    setNearBottom(true);
  }, [currentSessionId]);

  useEffect(() => {
    if (activeAgentRunId || nearBottom) {
      scrollToBottom(activeAgentRunId ? "auto" : "smooth");
    }
  }, [
    activeAgentRunId,
    currentRun?.progress,
    currentRun?.status,
    lastMessageId,
    nearBottom,
  ]);

  return (
    <div
      className="relative h-full overflow-y-auto"
      onScroll={() => {
        const element = scrollRef.current;

        if (!element) {
          return;
        }

        const distanceToBottom =
          element.scrollHeight - element.scrollTop - element.clientHeight;
        setNearBottom(distanceToBottom < 96);
      }}
      ref={scrollRef}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-6">
        {messages.length === 0 ? (
          <EmptyConversation />
        ) : null}
        {messages.map((message) => {
          const messageIndex = messages.findIndex((item) => item.id === message.id);
          const previousMessage = messageIndex > 0 ? messages[messageIndex - 1] : undefined;
          const waitStartedAt = message.waitStartedAt ?? previousMessage?.createdAt;
          const waitDurationMs = waitStartedAt
            ? new Date(message.createdAt).getTime() - new Date(waitStartedAt).getTime()
            : undefined;
          const messageArtifacts = artifacts.filter((artifact) =>
            message.artifactIds?.includes(artifact.id),
          );

          return (
            <div className="space-y-2" key={message.id}>
              {message.role === "user" ? (
                <UserMessage
                  content={message.content}
                  createdAt={message.createdAt}
                />
              ) : (
                <AssistantMessage
                  content={message.content}
                  createdAt={message.createdAt}
                  isPending={message.isPending}
                  pendingLabel={message.pendingLabel}
                  waitDurationMs={waitDurationMs}
                  waitStartedAt={message.waitStartedAt}
                />
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
        <div ref={bottomRef} />
      </div>
      {!nearBottom ? (
        <button
          className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full border bg-white px-3 py-1.5 text-xs text-muted-foreground shadow-sm hover:text-foreground"
          onClick={() => {
            scrollToBottom();
            setNearBottom(true);
          }}
          type="button"
        >
          <ArrowDown className="size-3.5" />
          {t("latestMessages")}
        </button>
      ) : null}
    </div>
  );
}
