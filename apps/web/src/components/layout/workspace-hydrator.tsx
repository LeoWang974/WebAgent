/**
 * File purpose: Renders and coordinates the workspace hydrator user-interface feature.
 * Main declarations: WorkspaceHydrator handles workspace hydrator.
 */

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useChatStore, useUserStore } from "@/stores";

export function WorkspaceHydrator() {
  const router = useRouter();
  const hydrateChat = useChatStore((state) => state.hydrate);
  const hydrateUser = useUserStore((state) => state.hydrate);
  const userHydrated = useUserStore((state) => state.hydrated);
  const user = useUserStore((state) => state.user);

  useEffect(() => {
    void hydrateChat();
    void hydrateUser();
  }, [hydrateChat, hydrateUser]);

  useEffect(() => {
    if (userHydrated && !user) {
      router.replace("/login");
    }
  }, [router, user, userHydrated]);

  return null;
}
