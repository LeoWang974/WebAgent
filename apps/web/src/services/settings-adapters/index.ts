import { fastApiSettingsAdapter } from "./fastapi-settings-adapter";
import { mockSettingsAdapter } from "./mock-settings-adapter";
import type { SettingsApiAdapter } from "./types";
import { resolveApiAdapterMode } from "../adapter-mode";

export type * from "./types";

const adapterMode = resolveApiAdapterMode();

export const settingsApi: SettingsApiAdapter =
  adapterMode === "fastapi" ? fastApiSettingsAdapter : mockSettingsAdapter;
