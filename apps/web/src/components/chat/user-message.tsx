import { MessageItem } from "./message-item";

interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return <MessageItem role="user" content={content} />;
}

