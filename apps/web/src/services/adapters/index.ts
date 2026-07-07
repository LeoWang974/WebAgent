import { fastApiAdapter } from "./fastapi-adapter";
import { mockAdapter } from "./mock-adapter";
import type { WebAgentApiAdapter } from "./types";

export type * from "./types";

const adapterMode = process.env.NEXT_PUBLIC_API_ADAPTER ?? "mock";

export const webAgentApi: WebAgentApiAdapter =
  adapterMode === "fastapi" ? fastApiAdapter : mockAdapter;
