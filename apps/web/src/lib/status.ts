import type { AgentRunStatus, SessionStatus } from "@/types";
import type { TranslationKey } from "./i18n";

export type UnifiedStatus =
  | AgentRunStatus
  | SessionStatus
  | "pending"
  | "active"
  | "ready";

export function getStatusLabelKey(status: UnifiedStatus): TranslationKey {
  if (status === "active" || status === "ready") {
    return "ready";
  }

  if (status === "tool_calling") {
    return "callingTools";
  }

  return status;
}

export function getStatusDotClass(status: UnifiedStatus) {
  if (status === "failed") {
    return "bg-red-500";
  }

  if (
    status === "queued" ||
    status === "pending" ||
    status === "running" ||
    status === "rendering" ||
    status === "tool_calling"
  ) {
    return "bg-amber-500";
  }

  if (status === "cancelled") {
    return "bg-zinc-400";
  }

  return "bg-emerald-500";
}
