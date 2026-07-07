import { MessageItem } from "./message-item";

interface AssistantMessageProps {
  content: string;
}

export function AssistantMessage({ content }: AssistantMessageProps) {
  return <MessageItem role="assistant" content={content} />;
}

