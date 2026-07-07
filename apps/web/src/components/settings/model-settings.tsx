import { ModelConfigCard } from "./model-config-card";

export function ModelSettings() {
  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold">Models</h2>
      <ModelConfigCard name="sensenova" provider="platform default" />
    </section>
  );
}

