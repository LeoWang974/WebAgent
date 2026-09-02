/**
 * File purpose: Manages client state and actions for chat store helpers.
 * Main declarations: createId handles create id; isTerminalRunStatus handles is terminal run
 * status; isDefaultSessionTitle handles is default session title; generateSessionTitle handles
 * generate session title; createPendingAssistantMessage handles create pending assistant message;
 * pendingMessageForRun handles pending message for run; hasPendingAssistantMessage handles has
 * pending assistant message.
 */

"use client";

import { useUiStore } from "./ui-store";
import type { AgentRun, Message } from "@/types";

export function createId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

export const TERMINAL_RUN_STATUSES: AgentRun["status"][] = [
  "completed",
  "failed",
  "cancelled",
  "disconnected",
];

export function isTerminalRunStatus(status: AgentRun["status"]) {
  return TERMINAL_RUN_STATUSES.includes(status);
}

export function isDefaultSessionTitle(title?: string) {
  const normalized = (title ?? "").trim().toLowerCase();
  return !normalized || normalized === "新对话" || normalized === "new conversation";
}

export function generateSessionTitle(content: string) {
  const cleaned = content.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "新任务";
  }
  return cleaned.length > 22 ? `${cleaned.slice(0, 22)}...` : cleaned;
}

export function createPendingAssistantMessage(
  sessionId: string,
  modelName: string,
  activity?: string,
  waitStartedAt?: string,
): Message {
  const now = new Date().toISOString();
  const language = useUiStore.getState().language;
  const pendingLabel = activity
    ? language === "zh-CN"
      ? `${modelName} 正在执行 ${activity}，等待阶段反馈...`
      : `${modelName} is running ${activity} and waiting for updates...`
    : language === "zh-CN"
      ? `${modelName} 正在工作，等待运行状态...`
      : `${modelName} is working and waiting for updates...`;

  return {
    id: createId("message_assistant_pending"),
    sessionId,
    role: "assistant",
    content: "",
    createdAt: now,
    isPending: true,
    pendingLabel,
    waitStartedAt: waitStartedAt ?? now,
  };
}

export function pendingMessageForRun(run: AgentRun, modelName = "Hermes"): Message {
  return createPendingAssistantMessage(
    run.sessionId,
    modelName,
    run.title === "Hermes Agent Run" ? undefined : run.title,
    run.startedAt,
  );
}

export function hasPendingAssistantMessage(messages: Message[], sessionId: string) {
  return messages.some(
    (message) =>
      message.sessionId === sessionId && message.role === "assistant" && message.isPending,
  );
}
