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
  username: "demo",
};

export const mockSkills: Skill[] = [
  {
    key: "data_analysis",
    name: "Data Analysis",
    description: "Upload datasets and generate tables, charts, and reports.",
    version: "1.0.0",
    enabled: true,
    isDefault: true,
    lastUpdatedAt: "2026-07-07T09:00:00.000Z",
  },
  {
    key: "deep_research",
    name: "Deep Research",
    description: "Turn a topic into a sourced research report.",
    version: "1.0.0",
    enabled: true,
    lastUpdatedAt: "2026-07-07T09:00:00.000Z",
  },
  {
    key: "ppt_generation",
    name: "PPT Generation",
    description: "Generate slide decks from topics or documents.",
    version: "1.0.0",
    enabled: true,
    lastUpdatedAt: "2026-07-07T09:00:00.000Z",
  },
  {
    key: "u1_image",
    name: "u1 Image",
    description: "Generate image results from prompts.",
    version: "1.0.0",
    enabled: true,
    lastUpdatedAt: "2026-07-07T09:00:00.000Z",
  },
];

export const mockSessions: Session[] = [
  {
    id: "session_1",
    title: "AI Agent market research",
    type: "deep_research",
    pinned: true,
    status: "active",
    updatedAt: "2026-07-07T13:00:00.000Z",
  },
  {
    id: "session_2",
    title: "Quarterly sales analysis",
    type: "data_analysis",
    pinned: false,
    status: "completed",
    updatedAt: "2026-07-07T12:20:00.000Z",
  },
  {
    id: "session_3",
    title: "Product launch deck",
    type: "ppt_generation",
    pinned: false,
    status: "completed",
    updatedAt: "2026-07-07T11:30:00.000Z",
  },
  {
    id: "session_4",
    title: "Campaign image concepts",
    type: "u1_image",
    pinned: false,
    status: "completed",
    updatedAt: "2026-07-07T10:45:00.000Z",
  },
];

export const mockMessages: Message[] = [
  {
    id: "message_1",
    sessionId: "session_1",
    role: "user",
    content: "Create an AI Agent market research report.",
    createdAt: "2026-07-07T13:01:00.000Z",
  },
  {
    id: "message_2",
    sessionId: "session_1",
    role: "assistant",
    content: "I prepared a rendered Markdown research report.",
    artifactIds: ["artifact_1"],
    createdAt: "2026-07-07T13:01:10.000Z",
  },
  {
    id: "message_3",
    sessionId: "session_2",
    role: "user",
    content: "Analyze which sales region is growing fastest.",
    createdAt: "2026-07-07T12:21:00.000Z",
  },
  {
    id: "message_4",
    sessionId: "session_2",
    role: "assistant",
    content: "The data preview is ready with sortable-looking rows and summary metrics.",
    artifactIds: ["artifact_2"],
    createdAt: "2026-07-07T12:21:10.000Z",
  },
  {
    id: "message_5",
    sessionId: "session_3",
    role: "user",
    content: "Generate a concise product launch presentation.",
    createdAt: "2026-07-07T11:31:00.000Z",
  },
  {
    id: "message_6",
    sessionId: "session_3",
    role: "assistant",
    content: "I generated a slide deck preview. The PPTX download will be wired later.",
    artifactIds: ["artifact_3"],
    createdAt: "2026-07-07T11:31:20.000Z",
  },
  {
    id: "message_7",
    sessionId: "session_4",
    role: "user",
    content: "Create four campaign image concepts for a modern AI workspace.",
    createdAt: "2026-07-07T10:46:00.000Z",
  },
  {
    id: "message_8",
    sessionId: "session_4",
    role: "assistant",
    content: "Four image concept previews are ready.",
    artifactIds: ["artifact_4"],
    createdAt: "2026-07-07T10:46:30.000Z",
  },
];

const aiAgentResearchMarkdown = `# AI Agent Market Research Report

## Summary

AI Agent products are moving from chat assistants toward task execution workspaces. For office, analytics, research, and content workflows, users increasingly care about **reliable execution**, **file outputs**, **context memory**, and **traceable progress**.

> The next competitive layer is not only model quality. It is the workflow around the model.

## Market Trends

| Trend | User Value | Product Implication |
| --- | --- | --- |
| Multi-model routing | Avoid vendor lock-in | Build a unified model gateway |
| Artifact previews | Generated work is immediately visible | Render Markdown, PPT, images, and data in the browser |
| Skill-based UX | Lower usage friction | Make analysis, research, slides, and images explicit entry points |
| Persistent context | Support ongoing work | Store sessions, summaries, files, and memories |

## Recommended MVP Scope

1. Codex-like two-column workspace
2. Default sensenova model
3. Four core skills
4. Real Markdown rendering
5. PPT, image, and data previews
6. API adapter layer for FastAPI integration

## Example Type

\`\`\`ts
type SkillKey =
  | "data_analysis"
  | "deep_research"
  | "ppt_generation"
  | "u1_image";
\`\`\`

## Risks

- Research requires source quality and citation handling.
- PPT rendering needs font and layout consistency.
- User-owned API keys must be encrypted.
- Long-running tasks need SSE or WebSocket progress.

## Next Step

Continue by turning every artifact type into a real browser preview, then connect each preview to persisted files from the backend.`;

export const mockArtifacts: Artifact[] = [
  {
    id: "artifact_1",
    sessionId: "session_1",
    type: "markdown_report",
    title: "AI Agent Market Research Report",
    status: "ready",
    content: aiAgentResearchMarkdown,
    metadata: {
      format: "markdown",
      wordCount: 360,
    },
  },
  {
    id: "artifact_2",
    sessionId: "session_2",
    type: "data_table",
    title: "Regional Sales Preview",
    status: "ready",
    metadata: {
      columns: ["Region", "Revenue", "Growth", "Pipeline", "Risk"],
      rows: [
        ["North", "$840k", "+18%", "$1.2M", "Low"],
        ["South", "$620k", "+11%", "$780k", "Medium"],
        ["East", "$970k", "+24%", "$1.5M", "Low"],
        ["West", "$710k", "+8%", "$690k", "High"],
        ["Central", "$560k", "+14%", "$820k", "Medium"],
      ],
      summary: [
        { label: "Top region", value: "East" },
        { label: "Avg growth", value: "+15%" },
        { label: "Total revenue", value: "$3.7M" },
      ],
    },
  },
  {
    id: "artifact_3",
    sessionId: "session_3",
    type: "ppt_deck",
    title: "Product Launch Deck",
    status: "ready",
    metadata: {
      slides: [
        {
          eyebrow: "Launch Plan",
          title: "WebAgent Product Launch",
          subtitle: "A focused workspace for agent-driven business tasks",
          bullets: ["Default model experience", "Four core skills", "Browser-native artifacts"],
        },
        {
          eyebrow: "Problem",
          title: "Users lose context across tools",
          subtitle: "Files, prompts, previews, and history live in separate places.",
          bullets: ["No unified workspace", "Manual rendering steps", "Hard to resume long tasks"],
        },
        {
          eyebrow: "Solution",
          title: "Agent workspace with live artifacts",
          subtitle: "Chat, skills, files, and generated outputs share one interface.",
          bullets: ["Persistent sessions", "SSE progress", "Markdown/PPT/image/data previews"],
        },
        {
          eyebrow: "Roadmap",
          title: "From mock UI to connected runtime",
          subtitle: "FastAPI, openclaw/hermes adapters, renderer, and storage.",
          bullets: ["API adapter", "Agent runs", "File rendering", "Skill versioning"],
        },
      ],
    },
  },
  {
    id: "artifact_4",
    sessionId: "session_4",
    type: "image_result",
    title: "AI Workspace Campaign Concepts",
    status: "ready",
    metadata: {
      images: [
        {
          id: "image_1",
          prompt: "A calm AI workspace dashboard with soft daylight",
          gradient: "linear-gradient(135deg, #d8eefe 0%, #f8f7ef 55%, #d8f3dc 100%)",
        },
        {
          id: "image_2",
          prompt: "Futuristic document generation interface",
          gradient: "linear-gradient(135deg, #f5d0fe 0%, #e0f2fe 50%, #fef3c7 100%)",
        },
        {
          id: "image_3",
          prompt: "Analyst reviewing charts generated by an agent",
          gradient: "linear-gradient(135deg, #d9f99d 0%, #bfdbfe 52%, #f5f5f4 100%)",
        },
        {
          id: "image_4",
          prompt: "Slide deck and research report floating in a browser workspace",
          gradient: "linear-gradient(135deg, #fecaca 0%, #fde68a 48%, #c7d2fe 100%)",
        },
      ],
    },
  },
];

export const mockModels: ModelConfig[] = [
  {
    baseUrl: "https://api.sensenova.cn/v1",
    id: "model_1",
    isAvailable: true,
    provider: "sensenova",
    name: "sensenova-default",
    isDefault: true,
  },
  {
    baseUrl: "https://api.openai-compatible.example/v1",
    id: "model_2",
    isAvailable: true,
    provider: "openai_compatible",
    name: "external-compatible",
    isDefault: false,
    maskedApiKey: "sk-****-demo",
  },
];
