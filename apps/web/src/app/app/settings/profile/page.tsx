import { ProfileSettings } from "@/components/settings";

export default function ProfileSettingsPage() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">个人信息</h1>
      <ProfileSettings />
    </main>
  );
}

