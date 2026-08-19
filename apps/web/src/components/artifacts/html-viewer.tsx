/**
 * File purpose: Renders and coordinates the html viewer user-interface feature.
 * Main declarations: HtmlViewer handles html viewer.
 */

"use client";

interface HtmlViewerProps {
  content: string;
  title: string;
}

export function HtmlViewer({ content, title }: HtmlViewerProps) {
  return (
    <article className="min-h-[520px] overflow-hidden rounded-lg border bg-white shadow-sm">
      <div className="border-b px-5 py-4">
        <h2 className="truncate text-base font-semibold">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">HTML 网页预览</p>
      </div>
      <iframe
        className="h-[640px] w-full bg-white"
        sandbox=""
        srcDoc={content}
        title={title}
      />
    </article>
  );
}
