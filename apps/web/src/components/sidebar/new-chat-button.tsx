"use client";

import { useChatStore, useUiStore } from "@/stores";
import { Plus } from "lucide-react";

export function NewChatButton() {
  const createSession = useChatStore((state) => state.createSession);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);

  return (
    <button
      className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white shadow-sm hover:bg-[#111]"
      onClick={() => {
        closeArtifactDrawer();
        createSession();
      }}
      type="button"
    >
      <Plus className="size-4" />
      New chat
    </button>
  );
}
