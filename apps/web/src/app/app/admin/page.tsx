const skills = [
  { name: "Data Analysis", version: "1.0.0", status: "Published" },
  { name: "Deep Research", version: "1.0.0", status: "Published" },
  { name: "PPT Generation", version: "1.0.0", status: "Published" },
  { name: "u1 Image", version: "1.0.0", status: "Published" },
];

export default function AdminPage() {
  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Admin
          </p>
          <h1 className="text-2xl font-semibold">Skill management</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            This placeholder keeps the skill update path visible. Later it will
            connect to skill version creation, publishing, rollback, and enable
            controls.
          </p>
        </header>

        <section className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <div className="grid grid-cols-[1fr_120px_140px_180px] border-b bg-[#f7f7f5] px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <span>Skill</span>
            <span>Version</span>
            <span>Status</span>
            <span>Actions</span>
          </div>
          {skills.map((skill) => (
            <div
              className="grid grid-cols-[1fr_120px_140px_180px] items-center border-b px-4 py-3 text-sm last:border-b-0"
              key={skill.name}
            >
              <span className="font-medium">{skill.name}</span>
              <span className="text-muted-foreground">{skill.version}</span>
              <span>
                <span className="rounded-full border bg-white px-2 py-1 text-xs text-muted-foreground">
                  {skill.status}
                </span>
              </span>
              <span className="flex gap-2">
                <button
                  className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                  type="button"
                >
                  New version
                </button>
                <button
                  className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                  type="button"
                >
                  Rollback
                </button>
              </span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}

