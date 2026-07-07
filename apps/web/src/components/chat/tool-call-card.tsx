interface ToolCallCardProps {
  name?: string;
  status?: "queued" | "running" | "completed" | "failed";
}

export function ToolCallCard({
  name = "tool",
  status = "queued",
}: ToolCallCardProps) {
  return (
    <div className="rounded-md border bg-muted/30 p-3 text-sm">
      <span className="font-medium">{name}</span>
      <span className="ml-2 text-muted-foreground">{status}</span>
    </div>
  );
}

