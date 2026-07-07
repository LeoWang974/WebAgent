import { ModelSettings } from "@/components/settings";

export default function ModelSettingsPage() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">模型配置</h1>
      <ModelSettings />
    </main>
  );
}

