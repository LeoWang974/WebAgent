/**
 * File purpose: Defines the Next.js page route or route layout.
 * Main declarations: AgentRunPage handles agent run page.
 */

import { AgentRunDetailView } from "@/components/agent-runs/agent-run-detail-view";

interface AgentRunPageProps {
  params: Promise<{ runId: string }>;
}

export default async function AgentRunPage({ params }: AgentRunPageProps) {
  const { runId } = await params;
  return <AgentRunDetailView runId={runId} />;
}
