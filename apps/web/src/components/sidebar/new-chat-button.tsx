"use client";

import { useChatStore, useUiStore } from "@/stores";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";

export function NewChatButton() {
  const { t } = useI18n();
  const router = useRouter();
  const createSession = useChatStore((state) => state.createSession);
  const closeArtifactDrawer = useUiStore((state) => state.closeArtifactDrawer);
  const closeSidebarDrawer = useUiStore((state) => state.closeSidebarDrawer);

  return (
    <button
      className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white shadow-sm hover:bg-[#111]"
      onClick={async () => {
        closeArtifactDrawer();
        closeSidebarDrawer();
        const session = await createSession();
        router.push(session ? `/app/chat/${session.id}` : "/app");
      }}
      type="button"
    >
      <Plus className="size-4" />
      {t("newChat")}
    </button>
  );
}
