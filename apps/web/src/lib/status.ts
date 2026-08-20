/**
 * File purpose: Provides shared browser utilities for status.
 * Main declarations: getStatusLabelKey handles get status label key; getStatusDotClass handles get
 * status dot class.
 */

import type { AgentRunStatus, SessionStatus } from "@/types";
import type { TranslationKey } from "./i18n";

export type UnifiedStatus =
  | AgentRunStatus
  | SessionStatus
  | "pending"
  | "staging"
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
    status === "staging" ||
    status === "running" ||
    status === "rendering" ||
    status === "tool_calling"
  ) {
    return "bg-amber-500";
  }

  if (status === "cancelled" || status === "disconnected") {
    return "bg-zinc-400";
  }

  return "bg-emerald-500";
}
