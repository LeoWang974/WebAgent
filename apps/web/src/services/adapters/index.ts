import { fastApiAdapter } from "./fastapi-adapter";
import { mockAdapter } from "./mock-adapter";
import type { WebAgentApiAdapter } from "./types";
import { resolveApiAdapterMode } from "../adapter-mode";

export type * from "./types";

const adapterMode = resolveApiAdapterMode();

export const webAgentApi: WebAgentApiAdapter =
  adapterMode === "fastapi" ? fastApiAdapter : mockAdapter;
