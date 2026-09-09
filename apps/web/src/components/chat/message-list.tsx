/**
 * File purpose: Renders and coordinates the message list user-interface feature.
 * Main declarations: MessageList handles message list.
 */

"use client";

import { ArtifactCard } from "../artifacts";
import { AssistantMessage } from "./assistant-message";
import { EmptyConversation } from "./empty-conversation";
import { UserMessage } from "./user-message";
import { useChatStore, useUiStore } from "@/stores";
import { ArrowDown } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { selectAgentStatusRun } from "./agent-status-model";
import type { Artifact, Message } from "@/types";

interface MessageRowProps {
  message: Message;
  deliveredAt: string;
  waitDurationMs?: number;
  artifacts: Artifact[];
  onArtifactClick: (artifactId: string) => void;
}

const MessageRow = memo(function MessageRow({
  message,
  deliveredAt,
  waitDurationMs,
  artifacts,
  onArtifactClick,
}: MessageRowProps) {
  return (
    <div className="space-y-2">
      {message.role === "user" ? (
        <UserMessage content={message.content} createdAt={message.createdAt} />
      ) : (
        <AssistantMessage
          content={message.content}
          createdAt={deliveredAt}
          isPending={message.isPending}
          pendingLabel={message.pendingLabel}
          waitDurationMs={waitDurationMs}
          waitStartedAt={message.waitStartedAt}
        />
      )}
      {artifacts.map((artifact) => (
        <ArtifactCard
          key={artifact.id}
          onClick={() => onArtifactClick(artifact.id)}
          status={artifact.status}
          title={artifact.title}
          type={artifact.type}
        />
      ))}
    </div>
  );
});

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
  const messages = useMemo(
    () =>
      Array.from(
        new Map(
          allMessages
            .filter((message) => message.sessionId === currentSessionId)
            .map((message) => [message.id, message]),
        ).values(),
      ),
    [allMessages, currentSessionId],
  );
  const sessionRuns = useMemo(
    () => agentRuns.filter((run) => run.sessionId === currentSessionId),
    [agentRuns, currentSessionId],
  );
  const currentRun = selectAgentStatusRun(agentRuns, currentSessionId);
  const deliveredAtByMessageId = useMemo(() => {
    const deliveredAt = new Map<string, string>();
    for (const run of sessionRuns) {
      for (const step of run.steps) {
        deliveredAt.set(step.id, step.timestamp);
      }
    }
    return deliveredAt;
  }, [sessionRuns]);
  const artifactsByMessageId = useMemo(() => {
    const byMessageId = new Map<string, Artifact[]>();
    const artifactsById = new Map(artifacts.map((artifact) => [artifact.id, artifact]));
    for (const message of messages) {
      const messageArtifacts = (message.artifactIds ?? [])
        .map((artifactId) => artifactsById.get(artifactId))
        .filter((artifact): artifact is Artifact => Boolean(artifact));
      byMessageId.set(message.id, messageArtifacts);
    }
    return byMessageId;
  }, [artifacts, messages]);
  const handleArtifactClick = useCallback(
    (artifactId: string) => {
      selectArtifact(artifactId);
      openArtifactDrawer();
    },
    [openArtifactDrawer, selectArtifact],
  );
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
        const nextNearBottom = distanceToBottom < 96;
        setNearBottom((previous) => (previous === nextNearBottom ? previous : nextNearBottom));
      }}
      ref={scrollRef}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-6">
        {messages.length === 0 ? (
          <EmptyConversation />
        ) : null}
        {messages.map((message, messageIndex) => {
          const previousMessage = messageIndex > 0 ? messages[messageIndex - 1] : undefined;
          const waitStartedAt = message.waitStartedAt ?? previousMessage?.createdAt;
          const deliveredAt =
            message.role === "assistant"
              ? deliveredAtByMessageId.get(message.id) ?? message.createdAt
              : message.createdAt;
          const waitDurationMs = waitStartedAt
            ? new Date(deliveredAt).getTime() - new Date(waitStartedAt).getTime()
            : undefined;
          const messageArtifacts = artifactsByMessageId.get(message.id) ?? [];

          return (
            <MessageRow
              artifacts={messageArtifacts}
              deliveredAt={deliveredAt}
              key={message.id}
              message={message}
              onArtifactClick={handleArtifactClick}
              waitDurationMs={waitDurationMs}
            />
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
