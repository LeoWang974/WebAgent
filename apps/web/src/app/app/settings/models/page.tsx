import { ModelSettings } from "@/components/settings";
import Link from "next/link";

export default function ModelSettingsPage() {
  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <Link
            className="text-sm text-muted-foreground hover:text-foreground"
            href="/app/settings"
          >
            Back to settings
          </Link>
          <h1 className="text-2xl font-semibold">Model configuration</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            Platform defaults use sensenova. User-owned external model settings
            will be added here later.
          </p>
        </header>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <ModelSettings />
        </section>
      </div>
    </main>
  );
}

