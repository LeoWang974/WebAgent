import { AgentRunDetailView } from "@/components/agent-runs/agent-run-detail-view";

interface AgentRunPageProps {
  params: Promise<{ runId: string }>;
}

export default async function AgentRunPage({ params }: AgentRunPageProps) {
  const { runId } = await params;
  return <AgentRunDetailView runId={runId} />;
}
