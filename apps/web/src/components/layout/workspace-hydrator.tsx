"use client";

import { useEffect } from "react";
import { useChatStore, useUserStore } from "@/stores";

export function WorkspaceHydrator() {
  const hydrateChat = useChatStore((state) => state.hydrate);
  const hydrateUser = useUserStore((state) => state.hydrate);

  useEffect(() => {
    void hydrateChat();
    void hydrateUser();
  }, [hydrateChat, hydrateUser]);

  return null;
}

