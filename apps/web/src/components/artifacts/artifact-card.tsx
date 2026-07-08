"use client";

import { FileText } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { getStatusLabelKey } from "@/lib/status";
import type { ArtifactStatus, ArtifactType } from "@/types";

interface ArtifactCardProps {
  onClick?: () => void;
  status?: ArtifactStatus;
  title: string;
  type: ArtifactType;
}

export function ArtifactCard({
  onClick,
  status = "ready",
  title,
  type,
}: ArtifactCardProps) {
  const { t } = useI18n();

  return (
    <button
      className="ml-10 flex w-[min(520px,calc(100%-2.5rem))] items-center gap-3 rounded-lg border bg-white p-3 text-left text-sm shadow-sm hover:bg-[#fafafa]"
      onClick={onClick}
      type="button"
    >
      <div className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-[#f7f7f5]">
        <FileText className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{title}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          {type} / {t(getStatusLabelKey(status))}
        </div>
      </div>
    </button>
  );
}
