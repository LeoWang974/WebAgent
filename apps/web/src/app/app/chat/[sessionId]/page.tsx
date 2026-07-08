import { ChatWorkspace } from "@/components/chat";

interface ChatSessionPageProps {
  params: Promise<{
    sessionId: string;
  }>;
}

export default async function ChatSessionPage({ params }: ChatSessionPageProps) {
  const { sessionId } = await params;

  return <ChatWorkspace sessionId={sessionId} />;
}

