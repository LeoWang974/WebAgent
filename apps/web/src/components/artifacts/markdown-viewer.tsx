/**
 * File purpose: Renders and coordinates the markdown viewer user-interface feature.
 * Main declarations: slugify handles slugify; extractToc handles extract toc; headingText handles
 * heading text; MarkdownViewer handles markdown viewer.
 */

"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { useI18n } from "@/lib/i18n";

interface MarkdownViewerProps {
  content: string;
  title?: string;
}

interface TocItem {
  id: string;
  level: number;
  text: string;
}

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

function extractToc(content: string) {
  const seen = new Map<string, number>();
  return content
    .split("\n")
    .flatMap<TocItem>((line) => {
      const match = /^(#{1,3})\s+(.+?)\s*$/.exec(line);
      if (!match) {
        return [];
      }
      const text = match[2].replace(/[#*_`[\]]/g, "").trim();
      const baseId = slugify(text) || "section";
      const count = seen.get(baseId) ?? 0;
      seen.set(baseId, count + 1);
      return [{ id: count ? `${baseId}-${count + 1}` : baseId, level: match[1].length, text }];
    });
}

function headingText(children: unknown): string {
  if (Array.isArray(children)) {
    return children.map(headingText).join("");
  }
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (children && typeof children === "object" && "props" in children) {
    return headingText((children as { props?: { children?: unknown } }).props?.children);
  }
  return "";
}

export function MarkdownViewer({ content, title }: MarkdownViewerProps) {
  const { t } = useI18n();
  const toc = useMemo(() => extractToc(content), [content]);
  const headingCounts = new Map<string, number>();

  function headingId(children: unknown) {
    const baseId = slugify(headingText(children)) || "section";
    const count = headingCounts.get(baseId) ?? 0;
    headingCounts.set(baseId, count + 1);
    return count ? `${baseId}-${count + 1}` : baseId;
  }

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
      <div className="grid gap-4 px-5 py-5 lg:grid-cols-[180px_minmax(0,1fr)]">
        {toc.length ? (
          <nav className="max-h-[70vh] overflow-y-auto rounded-lg border bg-[#fbfbfa] p-3 text-xs lg:sticky lg:top-3">
            <div className="mb-2 font-semibold text-foreground">目录</div>
            <div className="space-y-1">
              {toc.map((item) => (
                <a
                  className="block truncate rounded px-2 py-1 text-muted-foreground hover:bg-white hover:text-foreground"
                  href={`#${item.id}`}
                  key={item.id}
                  style={{ paddingLeft: 8 + (item.level - 1) * 10 }}
                >
                  {item.text}
                </a>
              ))}
            </div>
          </nav>
        ) : null}
        <div className="markdown-body min-w-0">
          <ReactMarkdown
            components={{
              h1: ({ children }) => (
                <h1 id={headingId(children)} className="scroll-mt-4">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 id={headingId(children)} className="scroll-mt-4">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 id={headingId(children)} className="scroll-mt-4">
                  {children}
                </h3>
              ),
            }}
            rehypePlugins={[rehypeHighlight]}
            remarkPlugins={[remarkGfm]}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </article>
  );
}
