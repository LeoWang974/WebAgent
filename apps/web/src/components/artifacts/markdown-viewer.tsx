"use client";

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { useI18n } from "@/lib/i18n";

interface MarkdownViewerProps {
  content: string;
  title?: string;
}

export function MarkdownViewer({ content, title }: MarkdownViewerProps) {
  const { t } = useI18n();

  return (
    <article className="min-h-[520px] rounded-lg border bg-white shadow-sm">
      <div className="border-b px-5 py-4">
        <h2 className="truncate text-base font-semibold">
          {title ?? "Markdown"}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("renderedMarkdownArtifact")}
        </p>
      </div>
      <div className="markdown-body px-5 py-5">
        <ReactMarkdown
          rehypePlugins={[rehypeHighlight]}
          remarkPlugins={[remarkGfm]}
        >
          {content}
        </ReactMarkdown>
      </div>
    </article>
  );
}
