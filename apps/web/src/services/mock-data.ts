import type { Artifact, Message, ModelConfig, Session, Skill, User } from "@/types";

export const mockUser: User = {
  id: "user_1",
  nickname: "WebAgent User",
  email: "user@example.com",
};

export const mockSkills: Skill[] = [
  {
    key: "data_analysis",
    name: "数据分析",
    description: "上传数据文件，生成分析、图表和报告。",
    version: "1.0.0",
    enabled: true,
  },
  {
    key: "deep_research",
    name: "深度调研",
    description: "围绕主题生成带来源的调研报告。",
    version: "1.0.0",
    enabled: true,
  },
  {
    key: "ppt_generation",
    name: "PPT 生成",
    description: "根据主题或文档生成可下载的 PPT。",
    version: "1.0.0",
    enabled: true,
  },
  {
    key: "u1_image",
    name: "u1 生图",
    description: "根据提示词生成图片结果。",
    version: "1.0.0",
    enabled: true,
  },
];

export const mockSessions: Session[] = [
  {
    id: "session_1",
    title: "AI Agent 市场调研",
    type: "deep_research",
    pinned: true,
    status: "active",
    updatedAt: "2026-07-07T13:00:00.000Z",
  },
  {
    id: "session_2",
    title: "季度销售数据分析",
    type: "data_analysis",
    pinned: false,
    status: "completed",
    updatedAt: "2026-07-07T12:20:00.000Z",
  },
  {
    id: "session_3",
    title: "产品发布 PPT 草稿",
    type: "ppt_generation",
    pinned: false,
    status: "running",
    updatedAt: "2026-07-07T11:30:00.000Z",
  },
];

export const mockMessages: Message[] = [
  {
    id: "message_1",
    sessionId: "session_1",
    role: "user",
    content: "帮我生成一份 AI Agent 市场调研报告。",
    createdAt: "2026-07-07T13:01:00.000Z",
  },
  {
    id: "message_2",
    sessionId: "session_1",
    role: "assistant",
    content: "我会先整理调研结构，并在右侧预留 Markdown 报告预览区域。",
    artifactIds: ["artifact_1"],
    createdAt: "2026-07-07T13:01:10.000Z",
  },
  {
    id: "message_3",
    sessionId: "session_2",
    role: "user",
    content: "分析这份销售表里哪个区域增长最快。",
    createdAt: "2026-07-07T12:21:00.000Z",
  },
  {
    id: "message_4",
    sessionId: "session_2",
    role: "assistant",
    content: "我会在后续版本中读取表格并生成图表。当前先展示数据表格预览占位。",
    artifactIds: ["artifact_2"],
    createdAt: "2026-07-07T12:21:10.000Z",
  },
];

export const mockArtifacts: Artifact[] = [
  {
    id: "artifact_1",
    sessionId: "session_1",
    type: "markdown_report",
    title: "AI Agent 市场调研报告",
    status: "ready",
  },
  {
    id: "artifact_2",
    sessionId: "session_2",
    type: "data_table",
    title: "销售数据预览",
    status: "ready",
  },
  {
    id: "artifact_3",
    sessionId: "session_3",
    type: "ppt_deck",
    title: "产品发布 PPT",
    status: "rendering",
  },
];

export const mockModels: ModelConfig[] = [
  {
    id: "model_1",
    provider: "sensenova",
    name: "sensenova-default",
    isDefault: true,
  },
];

