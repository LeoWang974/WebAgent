"use client";

import { useChatStore } from "@/stores";
import { BarChart3, Image, Presentation, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";

export function EmptyConversation() {
  const { t } = useI18n();
  const router = useRouter();
  const createSession = useChatStore((state) => state.createSession);
  const prompts = [
    {
      description: t("analyzeDataDescription"),
      example: "\u5206\u6790\u4e0a\u4f20\u8868\u683c\u4e2d\u7684\u9500\u552e\u8d8b\u52bf\uff0c\u627e\u51fa\u589e\u957f\u6700\u5feb\u7684\u533a\u57df\u3002",
      icon: BarChart3,
      id: "data-analysis",
      title: t("analyzeDataTitle"),
    },
    {
      description: t("deepResearchDescription"),
      example: "\u8c03\u7814 AI Agent \u5e02\u573a\u673a\u4f1a\uff0c\u8f93\u51fa\u5e26\u7ed3\u6784\u7684 Markdown \u62a5\u544a\u3002",
      icon: Search,
      id: "deep-research",
      title: t("deepResearch"),
    },
    {
      description: t("createPptDescription"),
      example: "\u56f4\u7ed5 WebAgent \u4ea7\u54c1\u53d1\u5e03\u751f\u6210 6 \u9875 PPT \u5927\u7eb2\u3002",
      icon: Presentation,
      id: "presentation",
      title: t("createPpt"),
    },
    {
      description: t("generateImageDescription"),
      example: "\u751f\u6210\u4e00\u7ec4\u73b0\u4ee3 AI \u5de5\u4f5c\u53f0\u5ba3\u4f20\u56fe\u6982\u5ff5\u3002",
      icon: Image,
      id: "image",
      title: t("generateImageTitle"),
    },
  ];

  return (
    <div className="mx-auto flex min-h-[420px] max-w-3xl flex-col justify-center py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">{t("emptyTitle")}</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          {t("emptyDescription")}
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {prompts.map((prompt) => {
          const Icon = prompt.icon;

          return (
            <button
              className="rounded-lg border bg-white p-4 text-left shadow-sm hover:bg-[#fafafa]"
              key={prompt.id}
              onClick={async () => {
                const session = await createSession();
                router.push(session ? `/app/chat/${session.id}` : "/app");
              }}
              type="button"
            >
              <div className="mb-3 flex size-9 items-center justify-center rounded-lg border bg-[#f7f7f5]">
                <Icon className="size-4" />
              </div>
              <div className="text-sm font-semibold">{prompt.title}</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {prompt.description}
              </p>
              <div className="mt-3 rounded-md border bg-[#f7f7f5] p-2 text-xs leading-5 text-muted-foreground">
                {prompt.example}
              </div>
              <div className="mt-3 text-xs font-medium text-foreground">
                {t("tryExample")}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
