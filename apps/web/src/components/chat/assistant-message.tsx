import { MessageItem } from "./message-item";

interface AssistantMessageProps {
  content: string;
  createdAt: string;
  isPending?: boolean;
  pendingLabel?: string;
  waitDurationMs?: number;
  waitStartedAt?: string;
}

export function AssistantMessage({
  content,
  createdAt,
  isPending,
  pendingLabel,
  waitDurationMs,
  waitStartedAt,
}: AssistantMessageProps) {
  return (
    <MessageItem
      role="assistant"
      content={content}
      createdAt={createdAt}
      isPending={isPending}
      pendingLabel={pendingLabel}
      waitDurationMs={waitDurationMs}
      waitStartedAt={waitStartedAt}
    />
  );
}
