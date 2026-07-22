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
  if (explicitSkillKey) {
    return explicitSkillKey;
  }

  const normalized = content.toLowerCase();
  const skillAliases: Array<[SkillKey, string[]]> = [
    ["deep_research", ["sn-deep-research", "deep research", "深度调研", "调研", "研究报告"]],
    ["data_analysis", ["sn-da", "data analysis", "数据分析", "分析数据", "表格分析"]],
    ["ppt_generation", ["sn-ppt", "ppt", "幻灯片", "演示文稿"]],
    ["u1_image", ["u1", "生图", "生成图片", "图片生成"]],
  ];

  return skillAliases.find(([, aliases]) =>
    aliases.some((alias) => normalized.includes(alias.toLowerCase())),
  )?.[0];
}

export function isDefaultSessionTitle(title?: string) {
  const normalized = (title ?? "").trim().toLowerCase();
  return !normalized || normalized === "新对话" || normalized === "new conversation";
}

export function generateSessionTitle(content: string, skillKey?: SkillKey) {
  const skillPrefix: Record<SkillKey, string> = {
    data_analysis: "数据分析",
    deep_research: "深度调研",
    ppt_generation: "PPT生成",
    u1_image: "图像生成",
  };
  const cleaned = content
    .replace(/[`*_>#\[\]{}()（）《》"“”'‘’]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^(请|帮我|帮我一下|麻烦|使用|基于|最后|现在|接下来|生成|分析|写一份|做一份)+/i, "")
    .trim();
  const compact = cleaned.length > 22 ? `${cleaned.slice(0, 22)}...` : cleaned;
  const fallback = skillKey ? skillPrefix[skillKey] : "新任务";
  return compact ? `${skillKey ? `${skillPrefix[skillKey]}：` : ""}${compact}` : fallback;
}

export function createPendingAssistantMessage(
  sessionId: string,
  modelName: string,
  requestedSkill?: string,
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
    waitStartedAt: now,
  };
}

export function pendingMessageForRun(run: AgentRun, modelName = "Agent"): Message {
  return createPendingAssistantMessage(
    run.sessionId,
    run.adapterKey ?? modelName,
    run.title === "Agent request" ? undefined : run.title,
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
