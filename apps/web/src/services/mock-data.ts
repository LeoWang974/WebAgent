import type {
  Artifact,
  Message,
  ModelConfig,
  Session,
  Skill,
  User,
} from "@/types";

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
    content: "我会先整理调研结构，并在右侧生成可阅读的 Markdown 报告。",
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
    content: "后续会读取表格并生成图表。当前先展示数据表格预览占位。",
    artifactIds: ["artifact_2"],
    createdAt: "2026-07-07T12:21:10.000Z",
  },
];

const aiAgentResearchMarkdown = `# AI Agent 市场调研报告

## 摘要

AI Agent 正从“聊天助手”转向“任务执行工作台”。在办公、数据分析、研发协作和内容生产场景中，用户更关注 **稳定执行、文件产出、上下文记忆** 和 **可追踪过程**。

> 结论：下一阶段的 Agent 产品竞争点不只是模型能力，而是完整工作流体验。

## 市场趋势

| 趋势 | 用户价值 | 产品启示 |
| --- | --- | --- |
| 多模型接入 | 降低单一供应商依赖 | 需要统一 Model Gateway |
| Artifact 预览 | 生成内容即刻可见 | Markdown/PPT/图片要网页内渲染 |
| Skill 化能力 | 降低使用门槛 | 数据分析、调研、PPT、生图应入口清晰 |
| 长上下文保存 | 支持持续任务 | 会话摘要、文件索引和记忆系统很关键 |

## 推荐 MVP 范围

1. 类 Codex 双栏 UI
2. 默认 sensenova 模型
3. 四个核心 skills
4. Markdown artifact 真渲染
5. PPT 和图片预览占位
6. 会话与上下文持久化接口预留

## 示例技术路线

\`\`\`ts
type SkillKey =
  | "data_analysis"
  | "deep_research"
  | "ppt_generation"
  | "u1_image";
\`\`\`

## 风险

- 深度调研需要来源可靠性与引用管理
- PPT 渲染需要解决字体和版式一致性
- 用户自定义 API Key 需要加密保存
- 长任务必须使用 SSE 或 WebSocket 展示进度

## 下一步

优先把 Markdown artifact 渲染打磨好，因为它是深度调研、数据分析报告和后续 PPT 大纲的共同基础。`;

export const mockArtifacts: Artifact[] = [
  {
    id: "artifact_1",
    sessionId: "session_1",
    type: "markdown_report",
    title: "AI Agent 市场调研报告",
    status: "ready",
    content: aiAgentResearchMarkdown,
    metadata: {
      format: "markdown",
      wordCount: 420,
    },
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

