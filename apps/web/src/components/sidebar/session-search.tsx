"use client";

import { useUiStore } from "@/stores";
import { Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function SessionSearch() {
  const { t } = useI18n();
  const query = useUiStore((state) => state.sessionSearchQuery);
  const setQuery = useUiStore((state) => state.setSessionSearchQuery);

  return (
    <div className="flex h-8 items-center gap-2 rounded-md border border-[#dfdfd8] bg-white/70 px-2">
      <Search className="size-3.5 text-muted-foreground" />
      <input
        className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
        data-session-search-input
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t("search")}
        type="search"
        value={query}
      />
    </div>
  );
}
