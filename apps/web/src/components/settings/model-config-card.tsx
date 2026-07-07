interface ModelConfigCardProps {
  name: string;
  provider: string;
}

export function ModelConfigCard({ name, provider }: ModelConfigCardProps) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-sm font-medium">{name}</div>
      <div className="text-xs text-muted-foreground">{provider}</div>
    </div>
  );
}

