"use client";

import { useUserStore } from "@/stores";

export function UserMenu() {
  const user = useUserStore((state) => state.user);
  const displayName = user?.nickname ?? "WebAgent User";
  const email = user?.email ?? "Loading profile";

  return (
    <button className="flex h-9 w-full items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-[#e9e9e2]">
      <span className="flex size-7 items-center justify-center rounded-full bg-[#242424] text-xs font-medium text-white">
        {displayName.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px]">{displayName}</span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {email}
        </span>
      </span>
    </button>
  );
}
