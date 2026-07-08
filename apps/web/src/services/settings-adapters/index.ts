import { fastApiSettingsAdapter } from "./fastapi-settings-adapter";
import { mockSettingsAdapter } from "./mock-settings-adapter";
import type { SettingsApiAdapter } from "./types";

export type * from "./types";

const adapterMode = process.env.NEXT_PUBLIC_API_ADAPTER ?? "mock";

export const settingsApi: SettingsApiAdapter =
  adapterMode === "fastapi" ? fastApiSettingsAdapter : mockSettingsAdapter;
