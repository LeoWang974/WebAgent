import { NewChatButton } from "../sidebar/new-chat-button";
import { SessionList } from "../sidebar/session-list";
import { SessionSearch } from "../sidebar/session-search";
import { SkillShortcuts } from "../sidebar/skill-shortcuts";
import { UserMenu } from "../sidebar/user-menu";
import { Settings } from "lucide-react";
import Link from "next/link";

export function Sidebar() {
  return (
    <aside className="flex h-screen w-[264px] shrink-0 flex-col border-r border-[#deded8] bg-[#f4f4ef]">
      <div className="space-y-3 border-b border-[#deded8] p-2.5">
        <div className="flex items-center gap-2 px-1.5">
          <div className="flex size-7 items-center justify-center rounded-md bg-[#242424] text-xs font-semibold text-white">
            W
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">WebAgent</div>
            <div className="text-[11px] text-muted-foreground">Agent workspace</div>
          </div>
        </div>
        <NewChatButton />
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-2.5">
        <SessionSearch />
        <SessionList />
        <SkillShortcuts />
      </div>
      <div className="space-y-1 border-t border-[#deded8] p-2.5">
        <Link
          className="flex h-8 items-center gap-2 rounded-md px-2 text-sm text-muted-foreground hover:bg-[#e9e9e2] hover:text-foreground"
          href="/app/settings"
        >
          <Settings className="size-4" />
          <span>Settings</span>
        </Link>
        <UserMenu />
      </div>
    </aside>
  );
}
