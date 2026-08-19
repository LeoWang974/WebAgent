/**
 * File purpose: Renders and coordinates the user message user-interface feature.
 * Main declarations: UserMessage handles user message.
 */

import { MessageItem } from "./message-item";

interface UserMessageProps {
  content: string;
  createdAt: string;
}

export function UserMessage({ content, createdAt }: UserMessageProps) {
  return <MessageItem role="user" content={content} createdAt={createdAt} />;
}
