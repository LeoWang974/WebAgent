/**
 * File purpose: Implements browser-side API access for index.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import { fastApiSettingsAdapter } from "./fastapi-settings-adapter";
import type { SettingsApiAdapter } from "./types";

export type * from "./types";

export const settingsApi: SettingsApiAdapter = fastApiSettingsAdapter;
