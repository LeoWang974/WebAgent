export default function AdminPage() {
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">管理后台</h1>
      <section className="rounded-lg border p-4">
        <h2 className="text-base font-semibold">Skills 版本管理</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          后续将在这里管理 skill 版本、发布、回滚和启用状态。
        </p>
      </section>
    </main>
  );
}

