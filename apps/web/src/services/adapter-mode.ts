export type ApiAdapterMode = "fastapi" | "mock";

const rawAdapterMode = process.env.NEXT_PUBLIC_API_ADAPTER;

export function resolveApiAdapterMode(): ApiAdapterMode {
  if (process.env.NODE_ENV === "production") {
    if (rawAdapterMode !== "fastapi") {
      throw new Error("NEXT_PUBLIC_API_ADAPTER=fastapi is required for production builds.");
    }

    return "fastapi";
  }

  if (rawAdapterMode === "fastapi" || rawAdapterMode === "mock") {
    return rawAdapterMode;
  }

  return "mock";
}
