import { ProfileSettings } from "@/components/settings";

export default function SettingsPage() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">设置</h1>
      <ProfileSettings />
    </main>
  );
}

