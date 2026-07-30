"use client";

import { useUiStore } from "./ui-store";
import type { AgentRun, Message, SkillKey } from "@/types";

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

export function detectRequestedSkill(
  content: string,
  explicitSkillKey?: SkillKey,
): SkillKey | undefined {
  void content;
  return explicitSkillKey;
}

export function isDefaultSessionTitle(title?: string) {
  const normalized = (title ?? "").trim().toLowerCase();
  return !normalized || normalized === "新对话" || normalized === "new conversation";
}

export function generateSessionTitle(content: string, skillKey?: SkillKey) {
  const skillPrefix: Record<SkillKey, string> = {
    data_analysis: "数据分析",
    deep_research: "深度调研",
    html_generation: "HTML生成",
    ppt_generation: "PPT生成",
    u1_image: "图像生成",
  };
  const cleaned = content
    .replace(/[`*_>#\[\]{}()（）《》“”‘’]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^(请|请帮我|帮我|麻烦|使用|基于|最后|现在|接下来|生成|分析|写一份|做一份)+/i, "")
    .trim();
  const compact = cleaned.length > 22 ? `${cleaned.slice(0, 22)}...` : cleaned;
  const fallback = skillKey ? skillPrefix[skillKey] : "新任务";
  return compact ? `${skillKey ? `${skillPrefix[skillKey]}：` : ""}${compact}` : fallback;
}

export function createPendingAssistantMessage(
  sessionId: string,
  modelName: string,
  requestedSkill?: string,
  waitStartedAt?: string,
): Message {
  const now = new Date().toISOString();
  const language = useUiStore.getState().language;
  const pendingLabel = requestedSkill
    ? language === "zh-CN"
      ? `${modelName} 正在执行 ${requestedSkill}，等待阶段反馈...`
      : `${modelName} is running ${requestedSkill} and waiting for runtime updates...`
    : language === "zh-CN"
      ? `${modelName} 正在工作，等待运行状态...`
      : `${modelName} is working and waiting for runtime updates...`;

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

export function pendingMessageForRun(run: AgentRun, modelName = "Agent"): Message {
  return createPendingAssistantMessage(
    run.sessionId,
    run.adapterKey ?? modelName,
    run.title === "Agent request" ? undefined : run.title,
    run.startedAt,
  );
}

export function hasPendingAssistantMessage(messages: Message[], sessionId: string) {
  return messages.some(
    (message) =>
      message.sessionId === sessionId &&
      message.role === "assistant" &&
      message.isPending,
  );
}
