import { ProfileSettings } from "@/components/settings";
import Link from "next/link";

export default function SettingsPage() {
  return (
    <main className="h-full overflow-y-auto bg-[#fbfbfa]">
      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">
        <header className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Workspace settings
          </p>
          <h1 className="text-2xl font-semibold">Settings</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            Manage profile preferences, default skills, model configuration, and
            future data controls from inside the WebAgent workspace.
          </p>
        </header>

        <nav className="flex flex-wrap gap-2">
          <Link
            className="rounded-md border bg-white px-3 py-2 text-sm shadow-sm hover:bg-muted"
            href="/app/settings/profile"
          >
            Profile
          </Link>
          <Link
            className="rounded-md border bg-white px-3 py-2 text-sm shadow-sm hover:bg-muted"
            href="/app/settings/models"
          >
            Models
          </Link>
          <Link
            className="rounded-md border bg-white px-3 py-2 text-sm shadow-sm hover:bg-muted"
            href="/app/admin"
          >
            Skill admin
          </Link>
        </nav>

        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <ProfileSettings />
        </section>
      </div>
    </main>
  );
}

