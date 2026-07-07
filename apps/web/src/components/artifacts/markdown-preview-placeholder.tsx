export function MarkdownPreviewPlaceholder() {
  return (
    <article className="min-h-[520px] rounded-lg border bg-white p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between border-b pb-3">
        <div>
          <h2 className="text-base font-semibold">AI Agent 市场调研报告</h2>
          <p className="mt-1 text-xs text-muted-foreground">Markdown preview</p>
        </div>
      </div>
      <div className="space-y-5 text-sm leading-7">
        <section>
          <h3 className="mb-2 text-sm font-semibold">1. 市场概览</h3>
          <p className="text-muted-foreground">
            这里会渲染 Agent 生成的 Markdown 内容，包括标题、表格、代码块和引用来源。
          </p>
        </section>
        <section>
          <h3 className="mb-2 text-sm font-semibold">2. 核心趋势</h3>
          <div className="space-y-2">
            <div className="h-3 w-full rounded bg-muted" />
            <div className="h-3 w-11/12 rounded bg-muted" />
            <div className="h-3 w-4/5 rounded bg-muted" />
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-sm font-semibold">3. 结论</h3>
          <div className="rounded-md border bg-[#f7f7f5] p-3 text-xs text-muted-foreground">
            Artifact renderer placeholder
          </div>
        </section>
      </div>
    </article>
  );
}

