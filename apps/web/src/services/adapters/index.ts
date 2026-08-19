/**
 * File purpose: Implements browser-side API access for index.
 * Main declarations: this file contains declarative configuration or re-exports and has no
 * callable declarations.
 */

import { fastApiAdapter } from "./fastapi-adapter";
import type { WebAgentApiAdapter } from "./types";

export type * from "./types";

export const webAgentApi: WebAgentApiAdapter = fastApiAdapter;
