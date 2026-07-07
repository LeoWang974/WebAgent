"use client";

import type { SkillKey } from "@/types";
import { useChatStore } from "@/stores";
import { BarChart3, Image, Presentation, Search } from "lucide-react";

const prompts: Array<{
  description: string;
  icon: typeof BarChart3;
  skillKey: SkillKey;
  title: string;
}> = [
  {
    description: "Upload a dataset and ask for trends, charts, and summaries.",
    icon: BarChart3,
    skillKey: "data_analysis",
    title: "Analyze data",
  },
  {
    description: "Turn a topic into a structured research report.",
    icon: Search,
    skillKey: "deep_research",
    title: "Deep research",
  },
  {
    description: "Draft slide structure and preview generated decks.",
    icon: Presentation,
    skillKey: "ppt_generation",
    title: "Create PPT",
  },
  {
    description: "Generate image concepts from a short prompt.",
    icon: Image,
    skillKey: "u1_image",
    title: "Generate image",
  },
];

export function EmptyConversation() {
  const createSession = useChatStore((state) => state.createSession);

  return (
    <div className="mx-auto flex min-h-[420px] max-w-3xl flex-col justify-center py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">What should WebAgent do?</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          Start with a plain request, or choose a skill to open a focused
          workspace. Generated files will appear as artifacts.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {prompts.map((prompt) => {
          const Icon = prompt.icon;

          return (
            <button
              className="rounded-xl border bg-white p-4 text-left shadow-sm hover:bg-[#fafafa]"
              key={prompt.skillKey}
              onClick={() => createSession(prompt.skillKey)}
              type="button"
            >
              <div className="mb-3 flex size-9 items-center justify-center rounded-lg border bg-[#f7f7f5]">
                <Icon className="size-4" />
              </div>
              <div className="text-sm font-semibold">{prompt.title}</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {prompt.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

